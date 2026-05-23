CREATE TABLE IF NOT EXISTS orphan_emails (
    id BIGSERIAL PRIMARY KEY,
    message_id VARCHAR(255) NOT NULL UNIQUE,
    from_email VARCHAR(255) NOT NULL,
    subject TEXT,
    body TEXT,
    attachments JSONB,
    raw_headers TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'matched', 'expired', 'manual_review')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orphan_emails_status ON orphan_emails(status);
CREATE INDEX IF NOT EXISTS idx_orphan_emails_message_id ON orphan_emails(message_id);
CREATE INDEX IF NOT EXISTS idx_orphan_emails_created_at ON orphan_emails(created_at);

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_orphan_emails_updated_at
    BEFORE UPDATE ON orphan_emails
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Добавляем колонку attachments в email_ai_queue (если еще не добавлена в 005)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='email_ai_queue' AND column_name='attachments') THEN
        ALTER TABLE email_ai_queue ADD COLUMN attachments JSONB;
    END IF;
END $$;
