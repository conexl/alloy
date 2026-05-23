-- Добавление статусов для rfq_sends
ALTER TABLE rfq_sends ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'sent';
ALTER TABLE rfq_sends ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE rfq_sends ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;

-- Индекс для статуса
CREATE INDEX IF NOT EXISTS idx_rfq_sends_status ON rfq_sends(status);

-- Добавление колонки для tracking
ALTER TABLE supplier_threads ADD COLUMN IF NOT EXISTS message_id VARCHAR(255);
ALTER TABLE supplier_threads ADD COLUMN IF NOT EXISTS in_reply_to VARCHAR(255);

-- Индекс для message_id
CREATE INDEX IF NOT EXISTS idx_supplier_threads_message_id ON supplier_threads(message_id);

-- Комментарии к новым колонкам
COMMENT ON COLUMN rfq_sends.status IS 'Статус отправки: sent, failed, delivered, bounced';
COMMENT ON COLUMN rfq_sends.error_message IS 'Сообщение об ошибке при отправке';
COMMENT ON COLUMN rfq_sends.retry_count IS 'Количество попыток отправки';
COMMENT ON COLUMN supplier_threads.message_id IS 'Message-ID письма';
COMMENT ON COLUMN supplier_threads.in_reply_to IS 'Message-ID на которое отвечаем';