package workers

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	"communication-service/internal/config"
	"communication-service/internal/domain"
	"communication-service/internal/repository"
	"communication-service/internal/services"

	"github.com/sirupsen/logrus"
	"go.uber.org/fx"
)

type AIBatchWorker struct {
	config           *config.Config
	logger           *logrus.Logger
	postgresRepo     *repository.PostgresRepository
	redisRepo        *repository.RedisRepository
	smtpClient       *services.SMTPClient
	quoteParser      *services.QuoteParser
	openRouterClient *services.OpenRouterClient

	shutdownCh chan struct{}
}

func NewAIBatchWorker(
	lc fx.Lifecycle,
	config *config.Config,
	logger *logrus.Logger,
	postgresRepo *repository.PostgresRepository,
	redisRepo *repository.RedisRepository,
	smtpClient *services.SMTPClient,
	quoteParser *services.QuoteParser,
	openRouterClient *services.OpenRouterClient,
) *AIBatchWorker {
	worker := &AIBatchWorker{
		config:           config,
		logger:           logger,
		postgresRepo:     postgresRepo,
		redisRepo:        redisRepo,
		smtpClient:       smtpClient,
		quoteParser:      quoteParser,
		openRouterClient: openRouterClient,
		shutdownCh:       make(chan struct{}),
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

func (w *AIBatchWorker) Start(ctx context.Context) {
	w.logger.Info("Starting AI batch worker")

	// Initial delay to let IMAP listener process emails first
	time.Sleep(30 * time.Second)

	for {
		select {
		case <-ctx.Done():
			w.logger.Info("AI batch worker stopped by context")
			return
		case <-w.shutdownCh:
			w.logger.Info("AI batch worker stopped by shutdown signal")
			return
		default:
			if err := w.processBatches(ctx); err != nil {
				w.logger.WithError(err).Error("Failed to process AI batches")
			}
			// Poll every 3 minutes
			select {
			case <-ctx.Done():
				return
			case <-w.shutdownCh:
				return
			case <-time.After(3 * time.Minute):
			}
		}
	}
}

func (w *AIBatchWorker) processBatches(ctx context.Context) error {
	// Get batch groups that are pending and old enough (3 min debounce)
	batchGroups, err := w.postgresRepo.GetPendingBatchGroups(ctx, 3)
	if err != nil {
		return fmt.Errorf("failed to get pending batches: %w", err)
	}

	if len(batchGroups) == 0 {
		return nil
	}

	w.logger.WithField("batches", len(batchGroups)).Info("Processing AI batches")

	for _, batchGroup := range batchGroups {
		if err := w.processBatchGroup(ctx, batchGroup); err != nil {
			w.logger.WithError(err).WithField("batch_group", batchGroup).Error("Failed to process batch group")
		}
	}

	return nil
}

func (w *AIBatchWorker) processBatchGroup(ctx context.Context, batchGroup string) error {
	emails, err := w.postgresRepo.GetPendingEmailsByBatchGroup(ctx, batchGroup)
	if err != nil {
		return err
	}

	if len(emails) == 0 {
		return nil
	}

	w.logger.WithFields(logrus.Fields{
		"batch_group": batchGroup,
		"emails":      len(emails),
	}).Info("Processing batch group")

	// Build batch requests
	var batchRequests []services.BatchEmailRequest
	var emailIndexMap = make(map[int]domain.QueuedEmail)

	for i, email := range emails {
		index := i + 1
		emailIndexMap[index] = email

		req := services.BatchEmailRequest{
			Index:   index,
			Body:    email.Body,
			Subject: email.Subject,
		}

		// Get item and RFQ context if available
		if email.ItemID != nil && email.RFQSendID != nil {
			item, rfq, err := w.postgresRepo.GetItemByID(ctx, *email.ItemID)
			if err == nil {
				req.Item = item
				req.RFQ = rfq

				// Get thread history for context (limit to last 3 messages)
				history, err := w.postgresRepo.GetThreadHistory(ctx, *email.RFQSendID)
				if err == nil && len(history) > 0 {
					if len(history) > 3 {
						history = history[len(history)-3:]
					}
					req.ThreadHistory = history
				}
			}

			// Get RFQ send for supplier_id
			rfqSend, err := w.postgresRepo.GetRFQSendByID(ctx, *email.RFQSendID)
			if err == nil && rfqSend != nil {
				req.SupplierID = rfqSend.SupplierID
				req.SupplierEmail = email.FromEmail

				// Get quote history for this supplier (limit to last 3)
				quoteHistory, err := w.postgresRepo.GetSupplierQuoteHistory(ctx, rfqSend.SupplierID, 3)
				if err == nil && len(quoteHistory) > 0 {
					req.QuoteHistory = quoteHistory
				}
			}
		}

		// Truncate body to reduce prompt size
		if len(req.Body) > 5000 {
			req.Body = req.Body[:5000] + "\n...[truncated]"
		}

		batchRequests = append(batchRequests, req)
	}

	// Send to AI - use individual analysis for single emails, batch for multiple
	var results []services.BatchAnalysisResult
	if len(batchRequests) == 1 {
		// Single email - use faster individual analysis
		req := batchRequests[0]
		individualReq := &services.EmailAnalysisRequest{
			Body: req.Body,
			Item: req.Item,
			RFQ:  req.RFQ,
		}
		var individualResult *services.EmailAnalysisResult
		for attempt := 0; attempt < 3; attempt++ {
			if attempt > 0 {
				w.logger.WithField("attempt", attempt+1).Info("Retrying AI individual analysis")
				time.Sleep(time.Duration(attempt*2) * time.Second)
			}
			individualResult, err = w.openRouterClient.AnalyzeEmail(ctx, individualReq)
			if err == nil {
				break
			}
			w.logger.WithError(err).WithField("attempt", attempt+1).Warn("AI individual analysis attempt failed")
		}
		if err != nil {
			if markErr := w.postgresRepo.MarkEmailsError(ctx, []int64{emails[0].ID}, err.Error()); markErr != nil {
				w.logger.WithError(markErr).Error("Failed to mark email as error")
			}
			return fmt.Errorf("AI individual analysis failed after retries: %w", err)
		}
		// Convert individual result to batch result
		action := individualResult.Action
		if action == "" {
			action = "question"
		}
		results = []services.BatchAnalysisResult{{
			Index:         1,
			Action:        action,
			Price:         individualResult.Price,
			DeliveryDays:  individualResult.DeliveryDays,
			PickupAddress: individualResult.PickupAddress,
			Reply:         individualResult.Reply,
		}}
	} else {
		// Multiple emails - use batch analysis
		for attempt := 0; attempt < 3; attempt++ {
			if attempt > 0 {
				w.logger.WithField("attempt", attempt+1).Info("Retrying AI batch analysis")
				time.Sleep(time.Duration(attempt*2) * time.Second)
			}
			results, err = w.openRouterClient.AnalyzeEmailBatch(ctx, batchRequests)
			if err == nil {
				break
			}
			w.logger.WithError(err).WithField("attempt", attempt+1).Warn("AI batch analysis attempt failed")
		}
		if err != nil {
			ids := make([]int64, len(emails))
			for i, e := range emails {
				ids[i] = e.ID
			}
			if markErr := w.postgresRepo.MarkEmailsError(ctx, ids, err.Error()); markErr != nil {
				w.logger.WithError(markErr).Error("Failed to mark emails as error")
			}
			return fmt.Errorf("AI batch analysis failed after retries: %w", err)
		}
	}

	// Process results
	var processedIDs []int64
	var aiResultDetails []string

	for _, result := range results {
		email, ok := emailIndexMap[result.Index]
		if !ok {
			w.logger.WithField("index", result.Index).Warn("AI result index not found in batch")
			continue
		}

		processedIDs = append(processedIDs, email.ID)

		if email.RFQSendID == nil {
			w.logger.WithField("email_id", email.ID).Warn("No RFQ send ID for email, skipping")
			continue
		}

		rfqSend, err := w.postgresRepo.GetRFQSendByID(ctx, *email.RFQSendID)
		if err != nil {
			w.logger.WithError(err).WithField("rfq_send_id", *email.RFQSendID).Warn("Failed to get RFQ send")
			continue
		}

		aiResultDetails = append(aiResultDetails, fmt.Sprintf("email_%d:%s", result.Index, result.Action))

		switch result.Action {
		case "quote":
			if result.Price != nil && *result.Price > 0 {
				pickupAddr := ""
				if result.PickupAddress != nil {
					pickupAddr = *result.PickupAddress
				}
				deliveryDays := 0
				if result.DeliveryDays != nil {
					deliveryDays = *result.DeliveryDays
				}
				quote := &domain.ParsedQuote{
					Price:         *result.Price,
					DeliveryDays:  deliveryDays,
					PickupAddress: &pickupAddr,
				}
				w.publishQuote(ctx, rfqSend, email.FromEmail, quote, email.Body)
			} else {
				// Quote action but no price — treat as question
				var item *domain.Item
				if email.ItemID != nil {
					item, _, _ = w.postgresRepo.GetItemByID(ctx, *email.ItemID)
				}
				// Try to get supplier email, but don't fail if not found
				supplierEmail, _ := w.postgresRepo.GetSupplierByEmail(ctx, email.FromEmail)
				w.handleQuestion(ctx, rfqSend, item, supplierEmail, email.FromEmail, result.Reply, email.Body, email.Subject)
			}

		case "visit_site":
			siteURL := ""
			if result.SiteURL != nil {
				siteURL = *result.SiteURL
			}
			w.logger.WithFields(logrus.Fields{
				"item_id":     rfqSend.ItemID,
				"supplier_id": rfqSend.SupplierID,
				"site_url":    siteURL,
			}).Info("Supplier refers to website price, saving for manual review")

			// Save as orphan for manual review
			w.postgresRepo.SaveOrphanEmail(ctx, &domain.OrphanEmail{
				MessageID:   email.MessageID,
				FromEmail:   email.FromEmail,
				Subject:     email.Subject,
				Body:        email.Body,
				LastError:   fmt.Sprintf("visit_site: %s", siteURL),
				Status:      "manual_review",
				RetryCount:  0,
			})

			// Save thread record
			w.postgresRepo.CreateSupplierThread(ctx, rfqSend.ID, "inbound", email.Body, true)

		case "unavailable":
			w.logger.WithFields(logrus.Fields{
				"item_id":     rfqSend.ItemID,
				"supplier_id": rfqSend.SupplierID,
			}).Info("Supplier does not have the item, marking as unavailable")

			// Save as orphan with unavailable status
			w.postgresRepo.SaveOrphanEmail(ctx, &domain.OrphanEmail{
				MessageID:   email.MessageID,
				FromEmail:   email.FromEmail,
				Subject:     email.Subject,
				Body:        email.Body,
				LastError:   "unavailable: item not available from this supplier",
				Status:      "unavailable",
				RetryCount:  0,
			})

			// Save thread record
			w.postgresRepo.CreateSupplierThread(ctx, rfqSend.ID, "inbound", email.Body, true)

		case "question":
			fallthrough
		default:
			var item *domain.Item
			if email.ItemID != nil {
				item, _, _ = w.postgresRepo.GetItemByID(ctx, *email.ItemID)
			}
			// Try to get supplier email, but don't fail if not found
			supplierEmail, _ := w.postgresRepo.GetSupplierByEmail(ctx, email.FromEmail)
			w.handleQuestion(ctx, rfqSend, item, supplierEmail, email.FromEmail, result.Reply, email.Body, email.Subject)
		}
	}

	// Mark processed
	if len(processedIDs) > 0 {
		aiResult := map[string]interface{}{
			"status":   "batch_processed",
			"results":  aiResultDetails,
			"count":    len(processedIDs),
			"group":    batchGroup,
		}
		aiResultJSON, err := json.Marshal(aiResult)
		if err != nil {
			w.logger.WithError(err).Error("Failed to marshal AI result")
		} else {
			if markErr := w.postgresRepo.MarkEmailsProcessed(ctx, processedIDs, string(aiResultJSON)); markErr != nil {
				w.logger.WithError(markErr).Error("Failed to mark emails as processed")
			}
		}
	}

	w.logger.WithFields(logrus.Fields{
		"batch_group": batchGroup,
		"processed":   len(processedIDs),
	}).Info("Batch group processed")

	return nil
}

func (w *AIBatchWorker) publishQuote(
	ctx context.Context,
	rfqSend *domain.RFQSend,
	fromEmail string,
	quote *domain.ParsedQuote,
	body string,
) error {
	pickupAddr := ""
	if quote.PickupAddress != nil {
		pickupAddr = *quote.PickupAddress
	}

	event := domain.QuoteReceivedEvent{
		ItemID:        strconv.FormatInt(rfqSend.ItemID, 10),
		SupplierID:    strconv.FormatInt(rfqSend.SupplierID, 10),
		SupplierEmail: fromEmail,
		Price:         strconv.FormatFloat(quote.Price, 'f', 2, 64),
		DeliveryDays:  strconv.Itoa(quote.DeliveryDays),
		PickupAddress: pickupAddr,
		Source:        "email",
	}

	if err := w.redisRepo.AddQuoteReceived(ctx, event); err != nil {
		w.logger.WithError(err).Error("Failed to publish quote to Redis")
		return err
	}

	if err := w.postgresRepo.CreateSupplierThread(ctx, rfqSend.ID, "inbound", body, false); err != nil {
		w.logger.WithError(err).Error("Failed to save supplier thread")
	}

	w.logger.WithFields(logrus.Fields{
		"item_id":       rfqSend.ItemID,
		"supplier_id":   rfqSend.SupplierID,
		"price":         quote.Price,
		"delivery_days": quote.DeliveryDays,
	}).Info("Quote received and published (batch)")

	return nil
}

func (w *AIBatchWorker) handleQuestion(
	ctx context.Context,
	rfqSend *domain.RFQSend,
	item *domain.Item,
	supplierEmail *domain.SupplierEmail,
	fromEmail string,
	reply string,
	body string,
	subject string,
) error {
	if reply == "" {
		reply = "Получил ваше сообщение. Уточню у коллег и вернусь с ответом."
	}

	testRecipient := "conexl@outlook.com"
	emailObj := &services.Email{
		To:         []string{testRecipient},
		Subject:    fmt.Sprintf("Re: %s", subject),
		TextBody:   reply,
		HTMLBody:   reply,
	}

	w.logger.WithFields(logrus.Fields{
		"item_id":       rfqSend.ItemID,
		"supplier_id":   rfqSend.SupplierID,
		"original_to":   fromEmail,
		"redirected_to": testRecipient,
	}).Info("Redirecting reply to test mailbox (batch)")

	result, err := w.smtpClient.Send(ctx, emailObj)
	if err != nil {
		return fmt.Errorf("failed to send reply: %w", err)
	}

	if err := w.postgresRepo.CreateSupplierThread(ctx, rfqSend.ID, "inbound", body, false); err != nil {
		w.logger.WithError(err).Error("Failed to save inbound thread")
	}

	if err := w.postgresRepo.CreateSupplierThread(ctx, rfqSend.ID, "outbound", reply, false); err != nil {
		w.logger.WithError(err).Error("Failed to save outbound thread")
	}

	w.logger.WithFields(logrus.Fields{
		"item_id":     rfqSend.ItemID,
		"supplier_id": rfqSend.SupplierID,
		"message_id":  result.MessageID,
	}).Info("Reply sent via AI (batch)")

	return nil
}
