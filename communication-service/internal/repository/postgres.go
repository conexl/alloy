package repository

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"communication-service/internal/domain"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/sirupsen/logrus"
)

type PostgresRepository struct {
	pool   *pgxpool.Pool
	logger *logrus.Logger
}

func NewPostgresRepository(dsn string, logger *logrus.Logger) (*PostgresRepository, error) {
	config, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to parse DSN: %w", err)
	}

	pool, err := pgxpool.NewWithConfig(context.Background(), config)
	if err != nil {
		return nil, fmt.Errorf("failed to create connection pool: %w", err)
	}

	if err := pool.Ping(context.Background()); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	logger.Info("Connected to PostgreSQL")
	return &PostgresRepository{pool: pool, logger: logger}, nil
}

func (r *PostgresRepository) Close() {
	r.pool.Close()
}

func (r *PostgresRepository) GetItemByID(ctx context.Context, itemID int64) (*domain.Item, *domain.RFQRequest, error) {
	query := `
        SELECT 
            i.id, i.name, i.tech_code, i.gost,
            i.unit, i.qty, i.deadline,
            i.location, i.payment_terms,
            i.tt_ol_ref, i.rkd_ref,
            i.rfq_id,
            r.id, r.city, r.total_budget
        FROM items i
        JOIN rfq_requests r ON r.id = i.rfq_id
        WHERE i.id = $1
    `

	var item domain.Item
	var rfq domain.RFQRequest

	err := r.pool.QueryRow(ctx, query, itemID).Scan(
		&item.ID, &item.Name, &item.TechCode, &item.GOST,
		&item.Unit, &item.Qty, &item.Deadline,
		&item.Location, &item.PaymentTerms,
		&item.TTOlRef, &item.RKDRef,
		&item.RFQID,
		&rfq.ID, &rfq.City, &rfq.TotalBudget,
	)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to get item: %w", err)
	}

	return &item, &rfq, nil
}

func (r *PostgresRepository) GetRFQSendByMessageID(ctx context.Context, messageID string) (*domain.RFQSend, *domain.Item, *domain.SupplierEmail, error) {
	query := `
        SELECT 
            rs.id, rs.item_id, rs.supplier_id, rs.smtp_message_id, rs.sent_at,
            i.id, i.name, i.tech_code, i.gost, i.unit, i.qty, i.deadline,
            i.location, i.payment_terms, i.tt_ol_ref, i.rkd_ref, i.rfq_id,
            se.supplier_id, se.email
        FROM rfq_sends rs
        JOIN items i ON i.id = rs.item_id
        JOIN supplier_emails se ON se.supplier_id = rs.supplier_id
        WHERE rs.smtp_message_id = $1
        LIMIT 1
    `

	var rfqSend domain.RFQSend
	var item domain.Item
	var supplierEmail domain.SupplierEmail

	err := r.pool.QueryRow(ctx, query, messageID).Scan(
		&rfqSend.ID, &rfqSend.ItemID, &rfqSend.SupplierID, &rfqSend.SMTPMessageID, &rfqSend.SentAt,
		&item.ID, &item.Name, &item.TechCode, &item.GOST, &item.Unit, &item.Qty, &item.Deadline,
		&item.Location, &item.PaymentTerms, &item.TTOlRef, &item.RKDRef, &item.RFQID,
		&supplierEmail.SupplierID, &supplierEmail.Email,
	)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("failed to get RFQ send: %w", err)
	}

	return &rfqSend, &item, &supplierEmail, nil
}

func (r *PostgresRepository) GetRFQSendByItemAndSupplier(ctx context.Context, itemID, supplierID int64) (*domain.RFQSend, error) {
	query := `
        SELECT id, item_id, supplier_id, smtp_message_id, sent_at
        FROM rfq_sends
        WHERE item_id = $1 AND supplier_id = $2
        LIMIT 1
    `

	var rfqSend domain.RFQSend
	err := r.pool.QueryRow(ctx, query, itemID, supplierID).Scan(
		&rfqSend.ID, &rfqSend.ItemID, &rfqSend.SupplierID, &rfqSend.SMTPMessageID, &rfqSend.SentAt,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to get RFQ send: %w", err)
	}

	return &rfqSend, nil
}

// GetSupplierByEmail returns supplier email record by email address
func (r *PostgresRepository) GetSupplierByEmail(ctx context.Context, email string) (*domain.SupplierEmail, error) {
	query := `
        SELECT supplier_id, email, is_valid
        FROM supplier_emails
        WHERE LOWER(email) = LOWER($1) AND is_valid = true
        LIMIT 1
    `

	var supplierEmail domain.SupplierEmail
	err := r.pool.QueryRow(ctx, query, email).Scan(
		&supplierEmail.SupplierID,
		&supplierEmail.Email,
		&supplierEmail.IsValid,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to get supplier by email: %w", err)
	}

	return &supplierEmail, nil
}

func (r *PostgresRepository) GetRFQSendByItemIDAndEmail(ctx context.Context, itemID int64, email string) (*domain.RFQSend, *domain.Item, *domain.SupplierEmail, error) {
	query := `
        SELECT 
            rs.id, rs.item_id, rs.supplier_id, rs.smtp_message_id, rs.sent_at,
            i.id, i.name, i.tech_code, i.gost, i.unit, i.qty, i.deadline,
            i.location, i.payment_terms, i.tt_ol_ref, i.rkd_ref, i.rfq_id,
            se.supplier_id, se.email
        FROM rfq_sends rs
        JOIN items i ON i.id = rs.item_id
        JOIN supplier_emails se ON se.supplier_id = rs.supplier_id
        WHERE rs.item_id = $1 AND se.email = $2 AND se.is_valid = true
        LIMIT 1
    `

	var rfqSend domain.RFQSend
	var item domain.Item
	var supplierEmail domain.SupplierEmail

	err := r.pool.QueryRow(ctx, query, itemID, email).Scan(
		&rfqSend.ID, &rfqSend.ItemID, &rfqSend.SupplierID, &rfqSend.SMTPMessageID, &rfqSend.SentAt,
		&item.ID, &item.Name, &item.TechCode, &item.GOST, &item.Unit, &item.Qty, &item.Deadline,
		&item.Location, &item.PaymentTerms, &item.TTOlRef, &item.RKDRef, &item.RFQID,
		&supplierEmail.SupplierID, &supplierEmail.Email,
	)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("failed to get RFQ send: %w", err)
	}

	return &rfqSend, &item, &supplierEmail, nil
}

func (r *PostgresRepository) GetRFQSendByItemID(ctx context.Context, itemID int64) (*domain.RFQSend, *domain.Item, *domain.SupplierEmail, error) {
	query := `
        SELECT 
            rs.id, rs.item_id, rs.supplier_id, rs.smtp_message_id, rs.sent_at,
            i.id, i.name, i.tech_code, i.gost, i.unit, i.qty, i.deadline,
            i.location, i.payment_terms, i.tt_ol_ref, i.rkd_ref, i.rfq_id,
            se.supplier_id, se.email
        FROM rfq_sends rs
        JOIN items i ON i.id = rs.item_id
        JOIN supplier_emails se ON se.supplier_id = rs.supplier_id
        WHERE rs.item_id = $1
        ORDER BY se.email
        LIMIT 1
    `

	var rfqSend domain.RFQSend
	var item domain.Item
	var supplierEmail domain.SupplierEmail

	err := r.pool.QueryRow(ctx, query, itemID).Scan(
		&rfqSend.ID, &rfqSend.ItemID, &rfqSend.SupplierID, &rfqSend.SMTPMessageID, &rfqSend.SentAt,
		&item.ID, &item.Name, &item.TechCode, &item.GOST, &item.Unit, &item.Qty, &item.Deadline,
		&item.Location, &item.PaymentTerms, &item.TTOlRef, &item.RKDRef, &item.RFQID,
		&supplierEmail.SupplierID, &supplierEmail.Email,
	)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("failed to get RFQ send: %w", err)
	}

	return &rfqSend, &item, &supplierEmail, nil
}

func (r *PostgresRepository) GetRFQSendByID(ctx context.Context, id int64) (*domain.RFQSend, error) {
	query := `
        SELECT id, item_id, supplier_id, smtp_message_id, sent_at
        FROM rfq_sends
        WHERE id = $1
        LIMIT 1
    `
	var rfqSend domain.RFQSend
	err := r.pool.QueryRow(ctx, query, id).Scan(
		&rfqSend.ID, &rfqSend.ItemID, &rfqSend.SupplierID, &rfqSend.SMTPMessageID, &rfqSend.SentAt,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to get RFQ send by ID: %w", err)
	}
	return &rfqSend, nil
}

func (r *PostgresRepository) CreateRFQSend(ctx context.Context, itemID, supplierID int64, smtpMessageID string) error {
	query := `
        INSERT INTO rfq_sends (item_id, supplier_id, smtp_message_id, sent_at)
        VALUES ($1, $2, $3, NOW())
    `

	_, err := r.pool.Exec(ctx, query, itemID, supplierID, smtpMessageID)
	if err != nil {
		return fmt.Errorf("failed to create RFQ send: %w", err)
	}

	return nil
}

func (r *PostgresRepository) CreateSupplierThread(ctx context.Context, rfqSendID int64, direction, body string, needsReview bool) error {
	query := `
        INSERT INTO supplier_threads (rfq_send_id, direction, body, needs_review, created_at)
        VALUES ($1, $2, $3, $4, NOW())
    `

	_, err := r.pool.Exec(ctx, query, rfqSendID, direction, body, needsReview)
	if err != nil {
		return fmt.Errorf("failed to create supplier thread: %w", err)
	}

	return nil
}

func (r *PostgresRepository) HasSupplierThread(ctx context.Context, rfqSendID int64, direction string) (bool, error) {
	query := `
        SELECT EXISTS(
            SELECT 1 FROM supplier_threads
            WHERE rfq_send_id = $1 AND direction = $2
        )
    `

	var exists bool
	err := r.pool.QueryRow(ctx, query, rfqSendID, direction).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("failed to check supplier thread: %w", err)
	}

	return exists, nil
}

func (r *PostgresRepository) MarkSupplierEmailInvalid(ctx context.Context, email string) error {
	query := `
        UPDATE supplier_emails
        SET is_valid = false
        WHERE email = $1
    `

	_, err := r.pool.Exec(ctx, query, email)
	if err != nil {
		return fmt.Errorf("failed to mark email invalid: %w", err)
	}

	return nil
}

func (r *PostgresRepository) GetUserProfileByRFQ(ctx context.Context, rfqID int64) (*domain.UserProfile, error) {
	query := `
        SELECT up.company_name, up.inn, up.kpp, up.address,
               up.phone, up.email, up.contact_person
        FROM rfq_requests r
        JOIN user_profiles up ON up.vk_id = r.created_by_vk
        WHERE r.id = $1
    `

	var profile domain.UserProfile
	err := r.pool.QueryRow(ctx, query, rfqID).Scan(
		&profile.CompanyName, &profile.Inn, &profile.Kpp,
		&profile.Address, &profile.Phone, &profile.Email,
		&profile.ContactPerson,
	)
	if err != nil {
		if err == pgx.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to get user profile: %w", err)
	}

	return &profile, nil
}

func (r *PostgresRepository) IsEmailProcessed(ctx context.Context, messageID string) (bool, error) {
	query := `SELECT EXISTS(SELECT 1 FROM processed_emails WHERE message_id = $1)`
	var exists bool
	err := r.pool.QueryRow(ctx, query, messageID).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("failed to check processed email: %w", err)
	}
	return exists, nil
}

func (r *PostgresRepository) MarkEmailProcessed(ctx context.Context, messageID, subject, fromEmail, status string) error {
	query := `
        INSERT INTO processed_emails (message_id, subject, from_email, status, processed_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (message_id) DO UPDATE SET
            status = EXCLUDED.status,
            processed_at = NOW()
    `
	_, err := r.pool.Exec(ctx, query, messageID, subject, fromEmail, status)
	if err != nil {
		return fmt.Errorf("failed to mark email processed: %w", err)
	}
	return nil
}

func (r *PostgresRepository) IsEmailInQueue(ctx context.Context, messageID string) (bool, error) {
	query := `SELECT EXISTS(SELECT 1 FROM email_ai_queue WHERE message_id = $1)`
	var exists bool
	err := r.pool.QueryRow(ctx, query, messageID).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("failed to check email queue: %w", err)
	}
	return exists, nil
}

func (r *PostgresRepository) SaveOrphanEmail(ctx context.Context, email *domain.OrphanEmail) error {
	attachmentsJSON, err := json.Marshal(email.Attachments)
	if err != nil {
		attachmentsJSON = []byte("[]")
	}

	query := `
        INSERT INTO orphan_emails (message_id, from_email, subject, body, attachments, raw_headers, retry_count, last_error, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (message_id) DO UPDATE SET
            retry_count = orphan_emails.retry_count + 1,
            last_error = EXCLUDED.last_error,
            status = EXCLUDED.status,
            updated_at = NOW()
    `
	_, err = r.pool.Exec(ctx, query,
		email.MessageID, email.FromEmail, email.Subject, email.Body,
		attachmentsJSON, email.RawHeaders, email.RetryCount, email.LastError, email.Status,
	)
	if err != nil {
		return fmt.Errorf("failed to save orphan email: %w", err)
	}
	return nil
}

func (r *PostgresRepository) GetPendingOrphanEmails(ctx context.Context, maxRetries int, minAgeMinutes int) ([]domain.OrphanEmail, error) {
	query := `
        SELECT id, message_id, from_email, subject, body, attachments, raw_headers, retry_count, last_error, status, created_at, updated_at
        FROM orphan_emails
        WHERE status = 'pending' AND retry_count < $1
          AND updated_at < NOW() - INTERVAL '1 minute' * $2
        ORDER BY created_at ASC
        LIMIT 50
    `
	rows, err := r.pool.Query(ctx, query, maxRetries, minAgeMinutes)
	if err != nil {
		return nil, fmt.Errorf("failed to get orphan emails: %w", err)
	}
	defer rows.Close()

	var emails []domain.OrphanEmail
	for rows.Next() {
		var e domain.OrphanEmail
		var attachments []string
		err := rows.Scan(
			&e.ID, &e.MessageID, &e.FromEmail, &e.Subject, &e.Body,
			&attachments, &e.RawHeaders, &e.RetryCount, &e.LastError, &e.Status,
			&e.CreatedAt, &e.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		e.Attachments = attachments
		emails = append(emails, e)
	}
	return emails, rows.Err()
}

func (r *PostgresRepository) UpdateOrphanEmailStatus(ctx context.Context, id int64, status string) error {
	query := `UPDATE orphan_emails SET status = $1, updated_at = NOW() WHERE id = $2`
	_, err := r.pool.Exec(ctx, query, status, id)
	if err != nil {
		return fmt.Errorf("failed to update orphan email: %w", err)
	}
	return nil
}

func (r *PostgresRepository) GetSupplierQuoteHistory(ctx context.Context, supplierID int64, limit int) ([]domain.QuoteHistory, error) {
	query := `
        SELECT i.name, q.price, q.delivery_days, q.pickup_address, q.received_at
        FROM quotes q
        JOIN items i ON i.id = q.item_id
        WHERE q.supplier_id = $1
        ORDER BY q.received_at DESC
        LIMIT $2
    `
	rows, err := r.pool.Query(ctx, query, supplierID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to get quote history: %w", err)
	}
	defer rows.Close()

	var history []domain.QuoteHistory
	for rows.Next() {
		var h domain.QuoteHistory
		err := rows.Scan(&h.ItemName, &h.Price, &h.DeliveryDays, &h.PickupAddress, &h.ReceivedAt)
		if err != nil {
			return nil, err
		}
		history = append(history, h)
	}
	return history, rows.Err()
}

func (r *PostgresRepository) EnqueueEmail(ctx context.Context, msg *domain.QueuedEmail) error {
	query := `
        INSERT INTO email_ai_queue 
        (message_id, supplier_email, rfq_id, item_id, subject, body, from_email, rfq_send_id, status, batch_group)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', $9)
        ON CONFLICT (message_id) DO NOTHING
    `
	_, err := r.pool.Exec(ctx, query,
		msg.MessageID, msg.SupplierEmail, msg.RFQID, msg.ItemID,
		msg.Subject, msg.Body, msg.FromEmail, msg.RFQSendID, msg.BatchGroup,
	)
	if err != nil {
		return fmt.Errorf("failed to enqueue email: %w", err)
	}
	return nil
}

func (r *PostgresRepository) GetPendingBatchGroups(ctx context.Context, minAgeMinutes int) ([]string, error) {
	query := `
        SELECT DISTINCT batch_group 
        FROM email_ai_queue 
        WHERE status = 'pending' 
          AND created_at < NOW() - INTERVAL '1 minute' * $1
        ORDER BY batch_group
    `
	rows, err := r.pool.Query(ctx, query, minAgeMinutes)
	if err != nil {
		return nil, fmt.Errorf("failed to get pending batches: %w", err)
	}
	defer rows.Close()

	var groups []string
	for rows.Next() {
		var g string
		if err := rows.Scan(&g); err != nil {
			return nil, err
		}
		groups = append(groups, g)
	}
	return groups, rows.Err()
}

func (r *PostgresRepository) GetPendingEmailsByBatchGroup(ctx context.Context, batchGroup string) ([]domain.QueuedEmail, error) {
	query := `
        SELECT id, message_id, supplier_email, rfq_id, item_id, subject, body, 
               from_email, rfq_send_id, status, batch_group, ai_result, error_message,
               created_at, processed_at
        FROM email_ai_queue 
        WHERE batch_group = $1 AND status = 'pending'
        ORDER BY created_at ASC
    `
	rows, err := r.pool.Query(ctx, query, batchGroup)
	if err != nil {
		return nil, fmt.Errorf("failed to get pending emails: %w", err)
	}
	defer rows.Close()

	var emails []domain.QueuedEmail
	for rows.Next() {
		var e domain.QueuedEmail
		var rfqID, itemID, rfqSendID *int64
		var aiResult, errMsg *string
		var processedAt *time.Time
		err := rows.Scan(
			&e.ID, &e.MessageID, &e.SupplierEmail, &rfqID, &itemID,
			&e.Subject, &e.Body, &e.FromEmail, &rfqSendID, &e.Status,
			&e.BatchGroup, &aiResult, &errMsg, &e.CreatedAt, &processedAt,
		)
		if err != nil {
			return nil, err
		}
		e.RFQID = rfqID
		e.ItemID = itemID
		e.RFQSendID = rfqSendID
		e.AIResult = aiResult
		e.ErrorMessage = errMsg
		e.ProcessedAt = processedAt
		emails = append(emails, e)
	}
	return emails, rows.Err()
}

func (r *PostgresRepository) GetThreadHistory(ctx context.Context, rfqSendID int64) ([]domain.ThreadMessage, error) {
	query := `
        SELECT direction, body, created_at
        FROM supplier_threads
        WHERE rfq_send_id = $1
        ORDER BY created_at ASC
    `
	rows, err := r.pool.Query(ctx, query, rfqSendID)
	if err != nil {
		return nil, fmt.Errorf("failed to get thread history: %w", err)
	}
	defer rows.Close()

	var messages []domain.ThreadMessage
	for rows.Next() {
		var m domain.ThreadMessage
		if err := rows.Scan(&m.Direction, &m.Body, &m.CreatedAt); err != nil {
			return nil, err
		}
		messages = append(messages, m)
	}
	return messages, rows.Err()
}

func (r *PostgresRepository) MarkEmailsProcessed(ctx context.Context, ids []int64, aiResult string) error {
	if len(ids) == 0 {
		return nil
	}
	query := `
        UPDATE email_ai_queue 
        SET status = 'done', ai_result = $1, processed_at = NOW()
        WHERE id = ANY($2)
    `
	_, err := r.pool.Exec(ctx, query, aiResult, ids)
	if err != nil {
		return fmt.Errorf("failed to mark emails processed: %w", err)
	}
	return nil
}

func (r *PostgresRepository) MarkEmailsError(ctx context.Context, ids []int64, errorMsg string) error {
	if len(ids) == 0 {
		return nil
	}
	query := `
        UPDATE email_ai_queue 
        SET status = 'error', error_message = $1, processed_at = NOW()
        WHERE id = ANY($2)
    `
	_, err := r.pool.Exec(ctx, query, errorMsg, ids)
	if err != nil {
		return fmt.Errorf("failed to mark emails error: %w", err)
	}
	return nil
}
