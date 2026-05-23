-- Таблица для отслеживания отправленных RFQ
CREATE TABLE IF NOT EXISTS rfq_sends (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL,
    supplier_id BIGINT NOT NULL,
    smtp_message_id VARCHAR(255) NOT NULL UNIQUE,
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Индексы для rfq_sends
CREATE INDEX IF NOT EXISTS idx_rfq_sends_item_id ON rfq_sends(item_id);
CREATE INDEX IF NOT EXISTS idx_rfq_sends_supplier_id ON rfq_sends(supplier_id);
CREATE INDEX IF NOT EXISTS idx_rfq_sends_item_supplier ON rfq_sends(item_id, supplier_id);
CREATE INDEX IF NOT EXISTS idx_rfq_sends_smtp_message_id ON rfq_sends(smtp_message_id);
CREATE INDEX IF NOT EXISTS idx_rfq_sends_sent_at ON rfq_sends(sent_at);

-- Таблица для хранения переписки с поставщиками
CREATE TABLE IF NOT EXISTS supplier_threads (
    id BIGSERIAL PRIMARY KEY,
    rfq_send_id BIGINT NOT NULL REFERENCES rfq_sends(id) ON DELETE CASCADE,
    direction VARCHAR(20) NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    body TEXT NOT NULL,
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Индексы для supplier_threads
CREATE INDEX IF NOT EXISTS idx_supplier_threads_rfq_send_id ON supplier_threads(rfq_send_id);
CREATE INDEX IF NOT EXISTS idx_supplier_threads_direction ON supplier_threads(direction);
CREATE INDEX IF NOT EXISTS idx_supplier_threads_needs_review ON supplier_threads(needs_review);
CREATE INDEX IF NOT EXISTS idx_supplier_threads_created_at ON supplier_threads(created_at);

-- Таблица для поставщиков (если нет в основной БД)
CREATE TABLE IF NOT EXISTS suppliers (
    id BIGSERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL UNIQUE,
    source_url TEXT,
    name VARCHAR(500),
    website VARCHAR(500),
    source VARCHAR(50) DEFAULT 'yandex',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Индексы для suppliers
CREATE INDEX IF NOT EXISTS idx_suppliers_domain ON suppliers(domain);
CREATE INDEX IF NOT EXISTS idx_suppliers_updated_at ON suppliers(updated_at);

-- Таблица для email поставщиков
CREATE TABLE IF NOT EXISTS supplier_emails (
    id BIGSERIAL PRIMARY KEY,
    supplier_id BIGINT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    source_url TEXT,
    page_type VARCHAR(100),
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(supplier_id, email)
);

-- Индексы для supplier_emails
CREATE INDEX IF NOT EXISTS idx_supplier_emails_supplier_id ON supplier_emails(supplier_id);
CREATE INDEX IF NOT EXISTS idx_supplier_emails_email ON supplier_emails(email);
CREATE INDEX IF NOT EXISTS idx_supplier_emails_is_valid ON supplier_emails(is_valid);

-- Таблица для связи поиска поставщиков с позициями
CREATE TABLE IF NOT EXISTS supplier_search_results (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL,
    supplier_id BIGINT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    search_query TEXT,
    rank INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'new',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(item_id, supplier_id)
);

-- Индексы для supplier_search_results
CREATE INDEX IF NOT EXISTS idx_supplier_search_results_item_id ON supplier_search_results(item_id);
CREATE INDEX IF NOT EXISTS idx_supplier_search_results_supplier_id ON supplier_search_results(supplier_id);
CREATE INDEX IF NOT EXISTS idx_supplier_search_results_status ON supplier_search_results(status);
CREATE INDEX IF NOT EXISTS idx_supplier_search_results_created_at ON supplier_search_results(created_at);

-- Таблица для логов поиска
CREATE TABLE IF NOT EXISTS search_log (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL,
    query TEXT NOT NULL,
    engine VARCHAR(50) NOT NULL,
    urls_found INTEGER DEFAULT 0,
    emails_found INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Индексы для search_log
CREATE INDEX IF NOT EXISTS idx_search_log_item_id ON search_log(item_id);
CREATE INDEX IF NOT EXISTS idx_search_log_created_at ON search_log(created_at);
CREATE INDEX IF NOT EXISTS idx_search_log_engine ON search_log(engine);

-- Таблица для items (если нет в основной БД)
CREATE TABLE IF NOT EXISTS items (
    id BIGSERIAL PRIMARY KEY,
    rfq_id BIGINT NOT NULL,
    name VARCHAR(500) NOT NULL,
    tech_code VARCHAR(200),
    gost VARCHAR(100),
    unit VARCHAR(50),
    qty DECIMAL(15, 3),
    deadline DATE,
    location VARCHAR(200),
    payment_terms TEXT,
    tt_ol_ref VARCHAR(200),
    rkd_ref VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Индексы для items
CREATE INDEX IF NOT EXISTS idx_items_rfq_id ON items(rfq_id);
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);

-- Таблица для rfq_requests (если нет в основной БД)
CREATE TABLE IF NOT EXISTS rfq_requests (
    id BIGSERIAL PRIMARY KEY,
    city VARCHAR(200),
    total_budget VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Индексы для rfq_requests
CREATE INDEX IF NOT EXISTS idx_rfq_requests_city ON rfq_requests(city);

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггеры для обновления updated_at
CREATE TRIGGER update_suppliers_updated_at
    BEFORE UPDATE ON suppliers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_supplier_search_results_updated_at
    BEFORE UPDATE ON supplier_search_results
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_items_updated_at
    BEFORE UPDATE ON items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_rfq_requests_updated_at
    BEFORE UPDATE ON rfq_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Комментарии к таблицам
COMMENT ON TABLE rfq_sends IS 'Отправленные RFQ письма поставщикам';
COMMENT ON TABLE supplier_threads IS 'Переписка с поставщиками по RFQ';
COMMENT ON TABLE suppliers IS 'Поставщики МТР';
COMMENT ON TABLE supplier_emails IS 'Email адреса поставщиков';
COMMENT ON TABLE supplier_search_results IS 'Результаты поиска поставщиков по позициям';
COMMENT ON TABLE search_log IS 'Логи поиска поставщиков';
COMMENT ON TABLE items IS 'Позиции МТР';
COMMENT ON TABLE rfq_requests IS 'Запросы коммерческих предложений';