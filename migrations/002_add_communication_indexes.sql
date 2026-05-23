-- Дополнительные индексы (без CONCURRENTLY для совместимости с init-скриптами)

CREATE INDEX IF NOT EXISTS idx_rfq_sends_item_supplier_sent ON rfq_sends(item_id, supplier_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_supplier_emails_email_valid ON supplier_emails(email, is_valid);
CREATE INDEX IF NOT EXISTS idx_supplier_threads_needs_review_created ON supplier_threads(needs_review, created_at);
CREATE INDEX IF NOT EXISTS idx_suppliers_updated_at_domain ON suppliers(updated_at, domain);
