package workers

import (
	"context"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"communication-service/internal/config"
	"communication-service/internal/domain"
	"communication-service/internal/repository"
	"communication-service/internal/services"

	"github.com/sirupsen/logrus"
	"go.uber.org/fx"
)

type IMAPListenerWorker struct {
	config           *config.Config
	logger           *logrus.Logger
	postgresRepo     *repository.PostgresRepository
	redisRepo        *repository.RedisRepository
	smtpClient       *services.SMTPClient
	quoteParser      *services.QuoteParser
	attachmentParser *services.AttachmentParser
	openRouterClient *services.OpenRouterClient

	shutdownCh chan struct{}

	rfqRegex *regexp.Regexp
}

func NewIMAPListenerWorker(
	lc fx.Lifecycle,
	config *config.Config,
	logger *logrus.Logger,
	postgresRepo *repository.PostgresRepository,
	redisRepo *repository.RedisRepository,
	smtpClient *services.SMTPClient,
	quoteParser *services.QuoteParser,
	attachmentParser *services.AttachmentParser,
	openRouterClient *services.OpenRouterClient,
) *IMAPListenerWorker {
	worker := &IMAPListenerWorker{
		config:           config,
		logger:           logger,
		postgresRepo:     postgresRepo,
		redisRepo:        redisRepo,
		smtpClient:       smtpClient,
		quoteParser:      quoteParser,
		attachmentParser: attachmentParser,
		openRouterClient: openRouterClient,
		shutdownCh:       make(chan struct{}),
		rfqRegex:         regexp.MustCompile(`#RFQ-(\d+)-(\d+)`),
	}

	lc.Append(fx.Hook{
		OnStart: func(ctx context.Context) error {
			go worker.Start(ctx)
			return nil
		},
		OnStop: func(ctx context.Context) error {
			close(worker.shutdownCh)
			return nil
		},
	})

	return worker
}

func (w *IMAPListenerWorker) Start(ctx context.Context) {
	w.logger.Info("Starting IMAP listener worker")

	for {
		select {
		case <-ctx.Done():
			w.logger.Info("IMAP listener worker stopped by context")
			return
		case <-w.shutdownCh:
			w.logger.Info("IMAP listener worker stopped by shutdown signal")
			return
		default:
			if err := w.checkAndProcessEmails(ctx); err != nil {
				w.logger.WithError(err).Error("Failed to process emails")
				time.Sleep(30 * time.Second)
			}
			time.Sleep(w.config.IMAPPollInterval)
		}
	}
}

func (w *IMAPListenerWorker) checkAndProcessEmails(ctx context.Context) error {
	// Collect all folders to check
	folders := []string{w.config.IMAPFolder}
	folders = append(folders, w.config.IMAPExtraFolders...)

	var allMessages []services.RawMessage
	seenMessageIDs := make(map[string]bool)

	for _, folder := range folders {
		messages, err := w.fetchFolder(ctx, folder)
		if err != nil {
			w.logger.WithError(err).WithField("folder", folder).Warn("Failed to fetch folder")
			continue
		}

		for _, msg := range messages {
			// Deduplicate by Message-ID across folders
			if msg.MessageID != "" {
				if seenMessageIDs[msg.MessageID] {
					continue
				}
				seenMessageIDs[msg.MessageID] = true
			}
			allMessages = append(allMessages, msg)
		}
	}

	w.logger.WithFields(logrus.Fields{
		"total":   len(allMessages),
		"folders": len(folders),
	}).Info("Fetched messages from all folders")

	var processed, skipped, failed, orphaned int
	for _, msg := range allMessages {
		// Deduplicate by Message-ID in DB
		if msg.MessageID != "" {
			alreadyProcessed, checkErr := w.postgresRepo.IsEmailProcessed(ctx, msg.MessageID)
			if checkErr != nil {
				w.logger.WithError(checkErr).WithField("message_id", msg.MessageID).Warn("Failed to check processed email")
			}
			if alreadyProcessed {
				skipped++
				continue
			}
		}

		// Also check if already in AI queue
		if msg.MessageID != "" {
			inQueue, checkErr := w.postgresRepo.IsEmailInQueue(ctx, msg.MessageID)
			if checkErr != nil {
				w.logger.WithError(checkErr).WithField("message_id", msg.MessageID).Warn("Failed to check AI queue")
			}
			if inQueue {
				skipped++
				continue
			}
		}

		success := w.processMessage(ctx, &msg)
		if success {
			processed++
			// Mark as seen
			if msg.MessageID != "" {
				if markErr := w.postgresRepo.MarkEmailProcessed(ctx, msg.MessageID, msg.Subject, w.extractEmail(msg.From), "processed"); markErr != nil {
					w.logger.WithError(markErr).Warn("Failed to mark email processed in DB")
				}
			}
		} else {
			// Check if it's an orphan (no RFQ match) or a real failure
			fromEmail := w.extractEmail(msg.From)
			_, _, _, matchErr := w.matchRFQ(ctx, &msg)
			if matchErr == nil {
				// No RFQ match - save as orphan for retry
				w.saveOrphanEmail(ctx, &msg, "no_rfq_match")
				orphaned++
			} else {
				failed++
			}
			if msg.MessageID != "" {
				if markErr := w.postgresRepo.MarkEmailProcessed(ctx, msg.MessageID, msg.Subject, fromEmail, "orphan"); markErr != nil {
					w.logger.WithError(markErr).Warn("Failed to mark email as orphan in DB")
				}
			}
		}
	}

	w.logger.WithFields(logrus.Fields{
		"total":     len(allMessages),
		"processed": processed,
		"skipped":   skipped,
		"failed":    failed,
		"orphaned":  orphaned,
	}).Info("Email batch processing completed")

	return nil
}

func (w *IMAPListenerWorker) fetchFolder(ctx context.Context, folder string) ([]services.RawMessage, error) {
	client := services.NewIMAPClient(
		w.config.IMAPHost,
		w.config.IMAPPort,
		w.config.IMAPUser,
		w.config.IMAPPass,
		folder,
		w.logger,
	)

	if err := client.Connect(); err != nil {
		return nil, fmt.Errorf("failed to connect to folder %s: %w", folder, err)
	}
	defer client.Close()

	messages, err := client.FetchRecent(3)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch from %s: %w", folder, err)
	}

	return messages, nil
}

func (w *IMAPListenerWorker) processMessage(ctx context.Context, msg *services.RawMessage) bool {
	fromEmail := w.extractEmail(msg.From)
	if fromEmail == "" {
		w.logger.Warn("No sender email in message")
		return false
	}

	// Try to match RFQ
	rfqSend, item, supplierEmail, err := w.matchRFQ(ctx, msg)
	if err != nil || rfqSend == nil {
		return false
	}

	// Extract text from body and attachments
	body := w.extractTextFromMessage(msg)
	if body == "" {
		w.logger.Warn("Empty email body and attachments")
		return false
	}
	msg.Body = body

	// Build batch group
	var rfqID int64
	if item != nil {
		rfqID = item.RFQID
	}
	batchGroup := fmt.Sprintf("%s:%d", fromEmail, rfqID)

	// Serialize attachments info for queue
	var attachmentNames []string
	for _, att := range msg.Attachments {
		attachmentNames = append(attachmentNames, att.Filename)
	}

	queuedEmail := &domain.QueuedEmail{
		MessageID:     msg.MessageID,
		SupplierEmail: supplierEmail.Email,
		RFQID:         &rfqID,
		ItemID:        &item.ID,
		Subject:       msg.Subject,
		Body:          body,
		FromEmail:     fromEmail,
		RFQSendID:     &rfqSend.ID,
		BatchGroup:    batchGroup,
	}

	if err := w.postgresRepo.EnqueueEmail(ctx, queuedEmail); err != nil {
		w.logger.WithError(err).WithField("message_id", msg.MessageID).Error("Failed to enqueue email")
		return false
	}

	w.logger.WithFields(logrus.Fields{
		"message_id":   msg.MessageID,
		"from":         fromEmail,
		"batch_group":  batchGroup,
		"rfq_send_id":  rfqSend.ID,
		"attachments":  len(msg.Attachments),
	}).Info("Email enqueued for batch AI processing")

	return true
}

func (w *IMAPListenerWorker) matchRFQ(ctx context.Context, msg *services.RawMessage) (*domain.RFQSend, *domain.Item, *domain.SupplierEmail, error) {
	// Try by In-Reply-To first
	if msg.InReplyTo != "" {
		rfqSend, item, supplierEmail, err := w.postgresRepo.GetRFQSendByMessageID(ctx, msg.InReplyTo)
		if err == nil && rfqSend != nil {
			w.logger.WithField("message_id", msg.InReplyTo).Info("Matched by In-Reply-To")
			return rfqSend, item, supplierEmail, nil
		}
	}

	// Try by parsing subject #RFQ-{rfq_id}-{item_id}
	rfqMatch := w.rfqRegex.FindStringSubmatch(msg.Subject)
	if len(rfqMatch) == 0 && msg.Body != "" {
		rfqMatch = w.rfqRegex.FindStringSubmatch(msg.Body)
		if len(rfqMatch) == 3 {
			w.logger.Info("Matched RFQ pattern in email body")
		}
	}

	if len(rfqMatch) == 3 {
		itemID, err := strconv.ParseInt(rfqMatch[2], 10, 64)
		if err != nil {
			return nil, nil, nil, fmt.Errorf("failed to parse item_id: %w", err)
		}

		fromEmail := w.extractEmail(msg.From)

		supplierEmail, err := w.postgresRepo.GetSupplierByEmail(ctx, fromEmail)
		if err != nil {
			// Fallback 1: try via rfq_sends
			rfqSend, item, supplierEmail, lookErr := w.postgresRepo.GetRFQSendByItemIDAndEmail(ctx, itemID, fromEmail)
			if lookErr != nil {
				// Fallback 2: domain match
				atIdx := strings.LastIndex(fromEmail, "@")
				if atIdx != -1 {
					domainPart := fromEmail[atIdx+1:]
					domainWithAt := fromEmail[atIdx:]
					domainEmail, domainErr := w.postgresRepo.GetSupplierByEmail(ctx, domainWithAt)
					if domainErr != nil || domainEmail == nil {
						domainEmail, domainErr = w.postgresRepo.GetSupplierByEmail(ctx, domainPart)
					}
					if domainErr == nil && domainEmail != nil {
						rfqSend, item, _, sendErr := w.postgresRepo.GetRFQSendByItemID(ctx, itemID)
						if sendErr == nil && rfqSend != nil {
							supplierEmail = domainEmail
							w.logger.WithFields(logrus.Fields{
								"item_id":     itemID,
								"supplier_id": rfqSend.SupplierID,
								"domain":      domainPart,
							}).Info("Matched by subject + domain fallback")
							return rfqSend, item, supplierEmail, nil
						}
					}
				}
				// Fallback 3: any rfq_send
				rfqSend, item, supplierEmail, sendErr := w.postgresRepo.GetRFQSendByItemID(ctx, itemID)
				if sendErr != nil {
					w.logger.WithError(err).WithField("email", fromEmail).Debug("Supplier not found")
					return nil, nil, nil, nil
				}
				w.logger.WithFields(logrus.Fields{
					"item_id":     itemID,
					"supplier_id": rfqSend.SupplierID,
				}).Info("Matched by subject + any rfq_send fallback")
				return rfqSend, item, supplierEmail, nil
			}
			w.logger.WithFields(logrus.Fields{
				"item_id":     itemID,
				"supplier_id": rfqSend.SupplierID,
			}).Info("Matched by subject + rfq_sends email fallback")
			return rfqSend, item, supplierEmail, nil
		}

		rfqSend, err := w.postgresRepo.GetRFQSendByItemAndSupplier(ctx, itemID, supplierEmail.SupplierID)
		if err != nil {
			w.logger.WithError(err).WithFields(logrus.Fields{
				"item_id":     itemID,
				"supplier_id": supplierEmail.SupplierID,
			}).Debug("RFQ send not found")
			return nil, nil, nil, nil
		}

		item, _, err := w.postgresRepo.GetItemByID(ctx, itemID)
		if err != nil {
			return nil, nil, nil, fmt.Errorf("failed to get item: %w", err)
		}

		w.logger.WithFields(logrus.Fields{
			"item_id":     itemID,
			"supplier_id": supplierEmail.SupplierID,
			"subject":     msg.Subject,
		}).Info("Matched by subject pattern")

		return rfqSend, item, supplierEmail, nil
	}

	return nil, nil, nil, nil
}

func (w *IMAPListenerWorker) saveOrphanEmail(ctx context.Context, msg *services.RawMessage, reason string) {
	fromEmail := w.extractEmail(msg.From)
	body := w.extractTextFromMessage(msg)

	var attachmentNames []string
	for _, att := range msg.Attachments {
		attachmentNames = append(attachmentNames, fmt.Sprintf("%s(%d bytes)", att.Filename, att.Size))
	}

	if err := w.postgresRepo.SaveOrphanEmail(ctx, &domain.OrphanEmail{
		MessageID:    msg.MessageID,
		FromEmail:    fromEmail,
		Subject:      msg.Subject,
		Body:         body,
		Attachments:  attachmentNames,
		RawHeaders:   fmt.Sprintf("From: %s\nTo: %s\nSubject: %s\nIn-Reply-To: %s", msg.From, msg.To, msg.Subject, msg.InReplyTo),
		LastError:    reason,
		Status:       "pending",
	}); err != nil {
		w.logger.WithError(err).WithField("message_id", msg.MessageID).Warn("Failed to save orphan email")
	} else {
		w.logger.WithFields(logrus.Fields{
			"message_id": msg.MessageID,
			"from":       fromEmail,
			"reason":     reason,
		}).Info("Saved orphan email for retry")
	}
}

func (w *IMAPListenerWorker) extractEmail(from string) string {
	start := strings.LastIndex(from, "<")
	end := strings.LastIndex(from, ">")
	if start != -1 && end != -1 && start < end {
		return strings.ToLower(from[start+1 : end])
	}
	return strings.ToLower(strings.TrimSpace(from))
}

var htmlTagRegex = regexp.MustCompile(`<[^>]+>`)
var htmlEntityRegex = regexp.MustCompile(`&#\d+;`)

func (w *IMAPListenerWorker) extractTextFromMessage(msg *services.RawMessage) string {
	var parts []string

	if msg.Body != "" {
		body := msg.Body
		// Strip HTML tags
		body = htmlTagRegex.ReplaceAllString(body, " ")
		// Decode HTML entities
		body = htmlEntityRegex.ReplaceAllStringFunc(body, func(s string) string {
			// Simple decoder for numeric entities
			var code int
			fmt.Sscanf(s, "&#%d;", &code)
			if code > 0 && code < 65536 {
				return string(rune(code))
			}
			return s
		})
		// Collapse whitespace
		body = regexp.MustCompile(`\s+`).ReplaceAllString(body, " ")
		body = strings.TrimSpace(body)
		if len(body) > 8000 {
			body = body[:8000] + "\n...[truncated]"
		}
		parts = append(parts, body)
	}

	// Extract text from attachments
	for _, att := range msg.Attachments {
		if att.Size > 10*1024*1024 { // Skip files > 10MB
			w.logger.WithField("filename", att.Filename).Warn("Attachment too large, skipping")
			continue
		}
		text := w.attachmentParser.ExtractText(&att)
		if text != "" {
			parts = append(parts, fmt.Sprintf("\n--- Attachment: %s ---\n%s", att.Filename, text))
		}
	}

	return strings.Join(parts, "\n")
}
