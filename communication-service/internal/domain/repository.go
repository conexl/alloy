package domain

import (
	"context"
)

type PostgreSQLRepository interface {
	GetItemByID(ctx context.Context, itemID int64) (*Item, *RFQRequest, error)
	GetRFQSendByMessageID(ctx context.Context, messageID string) (*RFQSend, *Item, *SupplierEmail, error)
	GetRFQSendByItemAndSupplier(ctx context.Context, itemID, supplierID int64) (*RFQSend, error)
	GetSupplierByEmail(ctx context.Context, email string) (*SupplierEmail, error)
	CreateRFQSend(ctx context.Context, itemID, supplierID int64, smtpMessageID string) error
	CreateSupplierThread(ctx context.Context, rfqSendID int64, direction, body string, needsReview bool) error
	MarkSupplierEmailInvalid(ctx context.Context, email string) error
	GetUserProfileByRFQ(ctx context.Context, rfqID int64) (*UserProfile, error)
	IsEmailProcessed(ctx context.Context, messageID string) (bool, error)
	MarkEmailProcessed(ctx context.Context, messageID, subject, fromEmail, status string) error
}

type RedisRepository interface {
	GetSuppliersFoundStream(ctx context.Context, consumerGroup, consumerID string) ([]SupplierFoundEvent, error)
	AddQuoteReceived(ctx context.Context, event QuoteReceivedEvent) error
	AcknowledgeMessage(ctx context.Context, stream, group, id string) error
	CreateConsumerGroup(ctx context.Context, stream, group string) error
}
