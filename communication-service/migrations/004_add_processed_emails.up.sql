-- Таблица для отслеживания обработанных входящих писем по Message-ID
CREATE TABLE IF NOT EXISTS processed_emails (
    message_id VARCHAR(512) PRIMARY KEY,
    subject VARCHAR(1000),
    from_email VARCHAR(255),
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'processed'
);

-- Индекс для быстрого поиска по времени
CREATE INDEX IF NOT EXISTS idx_processed_emails_processed_at ON processed_emails(processed_at);

-- Комментарии
COMMENT ON TABLE processed_emails IS 'Обработанные входящие email для дедупликации';
COMMENT ON COLUMN processed_emails.status IS 'Статус: processed, skipped_no_rfq, error';
