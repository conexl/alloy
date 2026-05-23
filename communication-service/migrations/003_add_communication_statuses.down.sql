-- Удаление колонок
ALTER TABLE rfq_sends DROP COLUMN IF EXISTS status;
ALTER TABLE rfq_sends DROP COLUMN IF EXISTS error_message;
ALTER TABLE rfq_sends DROP COLUMN IF EXISTS retry_count;

ALTER TABLE supplier_threads DROP COLUMN IF EXISTS message_id;
ALTER TABLE supplier_threads DROP COLUMN IF EXISTS in_reply_to;

-- Удаление индексов
DROP INDEX IF EXISTS idx_rfq_sends_status;
DROP INDEX IF EXISTS idx_supplier_threads_message_id;