package workers

import (
	"context"
	"fmt"
	"strings"
	"time"

	"communication-service/internal/config"
	"communication-service/internal/domain"
	"communication-service/internal/repository"
	"communication-service/internal/services"

	"github.com/sirupsen/logrus"
	"go.uber.org/fx"
)

type RFQSenderWorker struct {
	config          *config.Config
	logger          *logrus.Logger
	redisRepo       *repository.RedisRepository
	postgresRepo    *repository.PostgresRepository
	smtpClient      *services.SMTPClient
	templateService *services.TemplateService

	shutdownCh chan struct{}
}

func NewRFQSenderWorker(
	lc fx.Lifecycle,
	config *config.Config,
	logger *logrus.Logger,
	redisRepo *repository.RedisRepository,
	postgresRepo *repository.PostgresRepository,
	smtpClient *services.SMTPClient,
	templateService *services.TemplateService,
) *RFQSenderWorker {
	worker := &RFQSenderWorker{
		config:          config,
		logger:          logger,
		redisRepo:       redisRepo,
		postgresRepo:    postgresRepo,
		smtpClient:      smtpClient,
		templateService: templateService,
		shutdownCh:      make(chan struct{}),
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

func (w *RFQSenderWorker) Start(ctx context.Context) {
	w.logger.Info("Starting RFQ sender worker")

	// Create consumer group
	if err := w.redisRepo.CreateConsumerGroup(ctx, "suppliers_found", "comm-group"); err != nil {
		w.logger.WithError(err).Fatal("Failed to create consumer group")
		return
	}

	consumerID := fmt.Sprintf("comm-worker-%d", time.Now().Unix())

	for {
		select {
		case <-ctx.Done():
			w.logger.Info("RFQ sender worker stopped by context")
			return
		case <-w.shutdownCh:
			w.logger.Info("RFQ sender worker stopped by shutdown signal")
			return
		default:
			w.processMessages(ctx, consumerID)
			time.Sleep(1 * time.Second)
		}
	}
}

func (w *RFQSenderWorker) processMessages(ctx context.Context, consumerID string) {
	events, err := w.redisRepo.GetSuppliersFoundStream(ctx, "comm-group", consumerID)
	if err != nil {
		w.logger.WithError(err).Error("Failed to read from stream")
		return
	}

	for _, event := range events {
		if err := w.processEvent(ctx, &event); err != nil {
			w.logger.WithError(err).WithField("item_id", event.ItemID).Error("Failed to process event")
		} else {
			// Acknowledge message after successful processing
			if event.StreamMsgID != "" {
				if err := w.redisRepo.AcknowledgeMessage(ctx, "suppliers_found", "comm-group", event.StreamMsgID); err != nil {
					w.logger.WithError(err).WithField("msg_id", event.StreamMsgID).Error("Failed to acknowledge message")
				}
			}
		}
	}
}

func (w *RFQSenderWorker) processEvent(ctx context.Context, event *domain.SupplierFoundEvent) error {
	itemID, err := parseInt64(event.ItemID)
	if err != nil {
		return fmt.Errorf("invalid item_id: %w", err)
	}

	// Get item from database
	item, rfq, err := w.postgresRepo.GetItemByID(ctx, itemID)
	if err != nil {
		return fmt.Errorf("failed to get item: %w", err)
	}

	// Get user profile for the RFQ creator
	profile, err := w.postgresRepo.GetUserProfileByRFQ(ctx, rfq.ID)
	if err != nil {
		w.logger.WithError(err).WithField("rfq_id", rfq.ID).Warn("Failed to get user profile, continuing without it")
		profile = nil
	}

	var hasFailures bool

	// Send emails to each supplier
	for _, supplier := range event.Suppliers {
		// Limit emails per supplier if needed
		emailsToSend := supplier.Emails
		if len(emailsToSend) > w.config.MaxEmailsPerItem {
			emailsToSend = emailsToSend[:w.config.MaxEmailsPerItem]
			w.logger.WithField("item_id", itemID).Warn("Limited emails per supplier")
		}

		for _, email := range emailsToSend {
			if err := w.sendRFQToSupplier(ctx, item, rfq, profile, &supplier, email); err != nil {
				w.logger.WithError(err).WithFields(logrus.Fields{
					"item_id":     itemID,
					"supplier_id": supplier.SupplierID,
					"email":       email,
				}).Error("Failed to send RFQ")
				hasFailures = true
			}

			// Delay between emails
			time.Sleep(w.config.SMTPDelay)
		}
	}

	if hasFailures {
		return fmt.Errorf("some RFQ sends failed for item %d, will retry", itemID)
	}

	return nil
}

func (w *RFQSenderWorker) sendRFQToSupplier(
	ctx context.Context,
	item *domain.Item,
	rfq *domain.RFQRequest,
	profile *domain.UserProfile,
	supplier *domain.SupplierInfo,
	email string,
) error {
	// Check if already sent
	existing, err := w.postgresRepo.GetRFQSendByItemAndSupplier(ctx, item.ID, supplier.SupplierID)
	if err == nil && existing != nil {
		w.logger.WithFields(logrus.Fields{
			"item_id":     item.ID,
			"supplier_id": supplier.SupplierID,
			"email":       email,
		}).Info("Already sent RFQ to this supplier, skipping")
		return nil
	}

	// Render email
	htmlBody, textBody, err := w.templateService.RenderRFQ(item, rfq, profile)
	if err != nil {
		return fmt.Errorf("failed to render template: %w", err)
	}

	subject := w.templateService.GetSubject(item, rfq, profile)

	// Send email (redirect to test mailbox)
	testRecipient := "conexl@outlook.com"
	emailObj := &services.Email{
		To:       []string{testRecipient},
		Subject:  subject,
		HTMLBody: htmlBody,
		TextBody: textBody,
		ReplyTo:  w.config.SMTPFrom,
	}

	w.logger.WithFields(logrus.Fields{
		"item_id":      item.ID,
		"supplier_id":  supplier.SupplierID,
		"original_to":  email,
		"redirected_to": testRecipient,
	}).Info("Redirecting RFQ to test mailbox")

	result, err := w.smtpClient.Send(ctx, emailObj)
	if err != nil {
		// Check if email is invalid (550 User unknown)
		if strings.Contains(err.Error(), "550") {
			w.postgresRepo.MarkSupplierEmailInvalid(ctx, email)
		}
		return fmt.Errorf("failed to send email: %w", err)
	}

	// Save to database
	if err := w.postgresRepo.CreateRFQSend(ctx, item.ID, supplier.SupplierID, result.MessageID); err != nil {
		w.logger.WithError(err).Error("Failed to save RFQ send record")
		// Don't return error - email was sent successfully
	}

	w.logger.WithFields(logrus.Fields{
		"item_id":     item.ID,
		"supplier_id": supplier.SupplierID,
		"email":       email,
		"message_id":  result.MessageID,
	}).Info("RFQ email sent successfully")

	return nil
}

func parseInt64(s string) (int64, error) {
	var i int64
	_, err := fmt.Sscanf(s, "%d", &i)
	return i, err
}
