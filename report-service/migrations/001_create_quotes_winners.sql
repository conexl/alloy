-- Migration: Create tables for report service (quotes, winners)
-- Created: 2025-05-02

-- Quotes table - stores supplier quotes
CREATE TABLE IF NOT EXISTS quotes (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    supplier_email VARCHAR(255),
    price NUMERIC(12,2) NOT NULL,
    delivery_days INTEGER,
    pickup_address TEXT,
    source VARCHAR(32),
    received_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(item_id, supplier_id)
);

-- Winners table - stores selected winner for each item
CREATE TABLE IF NOT EXISTS winners (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL UNIQUE REFERENCES items(id) ON DELETE CASCADE,
    quote_id INTEGER NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    final_price NUMERIC(12,2) NOT NULL,
    margin_pct NUMERIC(5,2) NOT NULL,
    chosen_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_quotes_item_id ON quotes(item_id);
CREATE INDEX IF NOT EXISTS idx_quotes_supplier_id ON quotes(supplier_id);
CREATE INDEX IF NOT EXISTS idx_winners_item_id ON winners(item_id);