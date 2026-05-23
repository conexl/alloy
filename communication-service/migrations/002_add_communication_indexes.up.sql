-- Дополнительные индексы для оптимизации запросов

-- Составные индексы для частых запросов
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rfq_sends_item_supplier_sent ON rfq_sends(item_id, supplier_id, sent_at);

-- Индекс для поиска по email с фильтром валидности
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_supplier_emails_email_valid ON supplier_emails(email, is_valid);

-- Индекс для поиска непросмотренных тредов
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_supplier_threads_needs_review_created ON supplier_threads(needs_review, created_at);

-- Индекс для поиска свежих поставщиков
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_suppliers_updated_at_domain ON suppliers(updated_at, domain);

-- Партиционирование supplier_threads по дате (для больших объемов)
-- Создание партиций по месяцам
CREATE TABLE IF NOT EXISTS supplier_threads_2024_01 PARTITION OF supplier_threads
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE TABLE IF NOT EXISTS supplier_threads_2024_02 PARTITION OF supplier_threads
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

-- Продолжить для всех месяцев...