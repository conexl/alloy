-- Удаление триггеров
DROP TRIGGER IF EXISTS update_suppliers_updated_at ON suppliers;
DROP TRIGGER IF EXISTS update_supplier_search_results_updated_at ON supplier_search_results;
DROP TRIGGER IF EXISTS update_items_updated_at ON items;
DROP TRIGGER IF EXISTS update_rfq_requests_updated_at ON rfq_requests;

-- Удаление функции
DROP FUNCTION IF EXISTS update_updated_at_column();

-- Удаление таблиц (в порядке обратном созданию из-за внешних ключей)
DROP TABLE IF EXISTS supplier_threads;
DROP TABLE IF EXISTS rfq_sends;
DROP TABLE IF EXISTS supplier_search_results;
DROP TABLE IF EXISTS supplier_emails;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS search_log;
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS rfq_requests;