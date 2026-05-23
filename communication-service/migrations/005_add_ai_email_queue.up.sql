CREATE TABLE IF NOT EXISTS email_ai_queue (
    id BIGSERIAL PRIMARY KEY,
    message_id VARCHAR(255) NOT NULL UNIQUE,
    supplier_email VARCHAR(255) NOT NULL,
    rfq_id BIGINT,
    item_id BIGINT,
    subject TEXT,
    body TEXT,
    from_email VARCHAR(255) NOT NULL,
    rfq_send_id BIGINT REFERENCES rfq_sends(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'error')),
    batch_group VARCHAR(255) NOT NULL,
    ai_result JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_email_ai_queue_status ON email_ai_queue(status);
CREATE INDEX IF NOT EXISTS idx_email_ai_queue_batch ON email_ai_queue(batch_group, created_at);
CREATE INDEX IF NOT EXISTS idx_email_ai_queue_supplier ON email_ai_queue(supplier_email, status);
CREATE INDEX IF NOT EXISTS idx_email_ai_queue_created_at ON email_ai_queue(created_at);
