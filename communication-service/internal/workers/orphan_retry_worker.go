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

	"github.com/sirupsen/logrus"
	"go.uber.org/fx"
)

type OrphanRetryWorker struct {
	config       *config.Config
	logger       *logrus.Logger
	postgresRepo *repository.PostgresRepository
	shutdownCh   chan struct{}
}

func NewOrphanRetryWorker(
	lc fx.Lifecycle,
	config *config.Config,
	logger *logrus.Logger,
	postgresRepo *repository.PostgresRepository,
) *OrphanRetryWorker {
	worker := &OrphanRetryWorker{
		config:       config,
		logger:       logger,
		postgresRepo: postgresRepo,
		shutdownCh:   make(chan struct{}),
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

func (w *OrphanRetryWorker) Start(ctx context.Context) {
	w.logger.Info("Starting orphan retry worker")

	// Initial delay
	time.Sleep(5 * time.Minute)

	for {
		select {
		case <-ctx.Done():
			w.logger.Info("Orphan retry worker stopped by context")
			return
		case <-w.shutdownCh:
			w.logger.Info("Orphan retry worker stopped by shutdown signal")
			return
		default:
			if err := w.processOrphans(ctx); err != nil {
				w.logger.WithError(err).Error("Failed to process orphan emails")
			}
			select {
			case <-ctx.Done():
				return
			case <-w.shutdownCh:
				return
			case <-time.After(10 * time.Minute):
			}
		}
	}
}

func (w *OrphanRetryWorker) processOrphans(ctx context.Context) error {
	// Get orphans that are pending and haven't been retried recently
	orphans, err := w.postgresRepo.GetPendingOrphanEmails(ctx, 5, 10)
	if err != nil {
		return fmt.Errorf("failed to get orphan emails: %w", err)
	}

	if len(orphans) == 0 {
		return nil
	}

	w.logger.WithField("count", len(orphans)).Info("Processing orphan emails")

	var matched, expired, failed int
	for _, orphan := range orphans {
		// Try to find matching RFQ
		matchedSend, item, supplierEmail, matchErr := w.tryMatchOrphan(ctx, &orphan)
		if matchErr != nil {
			w.logger.WithError(matchErr).WithField("orphan_id", orphan.ID).Debug("Failed to match orphan")
			failed++
			continue
		}

		if matchedSend != nil {
			// Success! Enqueue for AI processing
			var rfqID int64
			if item != nil {
				rfqID = item.RFQID
			}
			batchGroup := fmt.Sprintf("%s:%d", orphan.FromEmail, rfqID)

			queuedEmail := &domain.QueuedEmail{
				MessageID:     orphan.MessageID,
				SupplierEmail: supplierEmail.Email,
				RFQID:         &rfqID,
				ItemID:        &item.ID,
				Subject:       orphan.Subject,
				Body:          orphan.Body,
				FromEmail:     orphan.FromEmail,
				RFQSendID:     &matchedSend.ID,
				BatchGroup:    batchGroup,
			}

			if err := w.postgresRepo.EnqueueEmail(ctx, queuedEmail); err != nil {
				w.logger.WithError(err).WithField("orphan_id", orphan.ID).Error("Failed to enqueue matched orphan")
				failed++
				continue
			}

			if err := w.postgresRepo.UpdateOrphanEmailStatus(ctx, orphan.ID, "matched"); err != nil {
				w.logger.WithError(err).Warn("Failed to update orphan status")
			}

			w.logger.WithFields(logrus.Fields{
				"orphan_id":   orphan.ID,
				"rfq_send_id": matchedSend.ID,
				"batch_group": batchGroup,
			}).Info("Orphan email matched and enqueued")
			matched++
		} else {
			// Check if too old (> 7 days)
			if time.Since(orphan.CreatedAt) > 7*24*time.Hour {
				w.postgresRepo.UpdateOrphanEmailStatus(ctx, orphan.ID, "expired")
				expired++
			} else {
				failed++
			}
		}
	}

	w.logger.WithFields(logrus.Fields{
		"total":   len(orphans),
		"matched": matched,
		"expired": expired,
		"failed":  failed,
	}).Info("Orphan retry completed")

	return nil
}

func (w *OrphanRetryWorker) tryMatchOrphan(ctx context.Context, orphan *domain.OrphanEmail) (*domain.RFQSend, *domain.Item, *domain.SupplierEmail, error) {
	// Try to parse RFQ pattern from subject or body
	rfqRegex := regexp.MustCompile(`#RFQ-(\d+)-(\d+)`)

	var text string
	if orphan.Subject != "" {
		text = orphan.Subject
	}
	if orphan.Body != "" {
		text += " " + orphan.Body
	}

	matches := rfqRegex.FindStringSubmatch(text)
	if len(matches) != 3 {
		return nil, nil, nil, nil
	}

	itemID, err := strconv.ParseInt(matches[2], 10, 64)
	if err != nil {
		return nil, nil, nil, err
	}

	// Try to find supplier by email
	supplierEmail, err := w.postgresRepo.GetSupplierByEmail(ctx, orphan.FromEmail)
	if err != nil {
		// Try domain fallback
		atIdx := strings.LastIndex(orphan.FromEmail, "@")
		if atIdx != -1 {
			domainPart := orphan.FromEmail[atIdx+1:]
			domainWithAt := orphan.FromEmail[atIdx:]
			domainEmail, domainErr := w.postgresRepo.GetSupplierByEmail(ctx, domainWithAt)
			if domainErr != nil || domainEmail == nil {
				domainEmail, domainErr = w.postgresRepo.GetSupplierByEmail(ctx, domainPart)
			}
			if domainErr == nil && domainEmail != nil {
				supplierEmail = domainEmail
			}
		}
		if supplierEmail == nil {
			// Try any rfq_send for this item
			rfqSend, item, se, err := w.postgresRepo.GetRFQSendByItemID(ctx, itemID)
			if err != nil {
				return nil, nil, nil, nil
			}
			return rfqSend, item, se, nil
		}
	}

	rfqSend, err := w.postgresRepo.GetRFQSendByItemAndSupplier(ctx, itemID, supplierEmail.SupplierID)
	if err != nil {
		return nil, nil, nil, err
	}

	item, _, err := w.postgresRepo.GetItemByID(ctx, itemID)
	if err != nil {
		return nil, nil, nil, err
	}

	return rfqSend, item, supplierEmail, nil
}
