package repository

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"communication-service/internal/domain"

	"github.com/go-redis/redis/v8"
	"github.com/sirupsen/logrus"
)

type RedisRepository struct {
	client *redis.Client
	logger *logrus.Logger
}

func NewRedisRepository(redisURL string, logger *logrus.Logger) (*RedisRepository, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse Redis URL: %w", err)
	}

	client := redis.NewClient(opt)

	if err := client.Ping(context.Background()).Err(); err != nil {
		return nil, fmt.Errorf("failed to connect to Redis: %w", err)
	}

	logger.Info("Connected to Redis")
	return &RedisRepository{client: client, logger: logger}, nil
}

func (r *RedisRepository) Close() error {
	return r.client.Close()
}

func (r *RedisRepository) CreateConsumerGroup(ctx context.Context, stream, group string) error {
	err := r.client.XGroupCreateMkStream(ctx, stream, group, "0").Err()
	if err != nil && err.Error() != "BUSYGROUP Consumer Group name already exists" {
		return fmt.Errorf("failed to create consumer group: %w", err)
	}
	return nil
}

func (r *RedisRepository) GetSuppliersFoundStream(ctx context.Context, consumerGroup, consumerID string) ([]domain.SupplierFoundEvent, error) {
	streams, err := r.client.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group:    consumerGroup,
		Consumer: consumerID,
		Streams:  []string{"suppliers_found", ">"},
		Count:    10,
		Block:    5 * time.Second,
	}).Result()

	if err == redis.Nil {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to read stream: %w", err)
	}

	var events []domain.SupplierFoundEvent
	for _, stream := range streams {
		for _, message := range stream.Messages {
			var suppliers []domain.SupplierInfo
			if suppliersStr, ok := message.Values["suppliers"].(string); ok {
				if err := json.Unmarshal([]byte(suppliersStr), &suppliers); err != nil {
					r.logger.WithError(err).Error("Failed to unmarshal suppliers")
					continue
				}
			}

			itemID, _ := message.Values["item_id"].(string)
			itemName, _ := message.Values["item_name"].(string)
			emailsCount, _ := message.Values["emails_count"].(string)

			event := domain.SupplierFoundEvent{
				ItemID:      itemID,
				ItemName:    itemName,
				EmailsCount: emailsCount,
				Suppliers:   suppliers,
				StreamMsgID: message.ID,
			}
			events = append(events, event)
		}
	}

	return events, nil
}

func (r *RedisRepository) AddQuoteReceived(ctx context.Context, event domain.QuoteReceivedEvent) error {
	values := map[string]interface{}{
		"item_id":        event.ItemID,
		"supplier_id":    event.SupplierID,
		"supplier_email": event.SupplierEmail,
		"price":          event.Price,
		"delivery_days":  event.DeliveryDays,
		"pickup_address": event.PickupAddress,
		"source":         event.Source,
	}

	_, err := r.client.XAdd(ctx, &redis.XAddArgs{
		Stream: "quote_received",
		Values: values,
	}).Result()

	if err != nil {
		return fmt.Errorf("failed to add quote to stream: %w", err)
	}

	return nil
}

func (r *RedisRepository) AcknowledgeMessage(ctx context.Context, stream, group, id string) error {
	return r.client.XAck(ctx, stream, group, id).Err()
}
