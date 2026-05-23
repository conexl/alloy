# Report Service

Сервис генерации отчетов на основе котировок поставщиков.

## Назначение

- **Quote Worker** — потребляет сообщения из Redis Stream `quote_received`, сохраняет котировки, пересчитывает победителя
- **HTTP API** — отдает статус обработки и генерирует Excel-отчеты

## Стек

- Python 3.11
- FastAPI — HTTP сервер
- asyncpg — PostgreSQL клиент
- redis-py — Redis клиент
- pandas + openpyxl — генерация Excel
- pydantic-settings — конфигурация

## Переменные окружения

```bash
DB_DSN=postgresql://...
REDIS_URL=redis://...
HTTP_PORT=8080
MARGIN_PERCENT=15
REPORT_DIR=./reports
```

## API Endpoints

### `GET /health`

```json
{"status": "ok", "db": "ok", "redis": "ok"}
```

### `GET /report/{rfq_id}/status`

Возвращает статус обработки RFQ:

```json
{
  "rfq_id": 42,
  "total": 50,
  "quoted": 38,
  "winners": 35,
  "ready": false
}
```

### `POST /report/{rfq_id}/generate`

Генерирует и возвращает Excel-файл.

**Ответы:**
- `200` — файл готов
- `404` — RFQ не найден или нет котировок (`code: RFQ_NOT_FOUND` или `code: NO_QUOTES`)
- `500` — внутренняя ошибка

### `GET /report/{rfq_id}/file`

Возвращает ранее сохраненный файл (используется telegram-bot'ом).

## Архитектура

```
report-service/
├── cmd/
│   └── main.py              # Точка входа
├── internal/
│   ├── config/
│   │   └── config.py        # Конфигурация (pydantic-settings)
│   ├── domain/
│   │   ├── models.py        # Доменные модели
│   │   └── repository.py    # Интерфейсы репозиториев
│   ├── repository/
│   │   ├── postgres.py      # PostgreSQL реализация
│   │   └── redis.py         # Redis реализация
│   ├── services/
│   │   ├── aggregator.py    # Алгоритм выбора победителя
│   │   ├── excel.py         # Генерация Excel
│   │   └── report.py        # Оркестрация генерации
│   ├── workers/
│   │   └── quote_worker.py  # Потребитель quote_received
│   ├── handlers/
│   │   └── report.py        # HTTP обработчики
│   └── app/
│       └── app.py           # Фабрика приложения, DI
├── Dockerfile
└── .env.example
```

## База данных

### Таблица `quotes`

```sql
CREATE TABLE quotes (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    supplier_email VARCHAR(255),
    price NUMERIC(12,2) NOT NULL,
    delivery_days INTEGER,
    pickup_address TEXT,
    source VARCHAR(32),
    received_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(item_id, supplier_id)
);
```

### Таблица `winners`

```sql
CREATE TABLE winners (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL UNIQUE REFERENCES items(id),
    quote_id INTEGER NOT NULL REFERENCES quotes(id),
    final_price NUMERIC(12,2) NOT NULL,
    margin_pct NUMERIC(5,2) NOT NULL,
    chosen_at TIMESTAMP DEFAULT NOW()
);
```

## Алгоритм выбора победителя

1. Загружаются все котировки для позиции
2. Фильтр по сроку: `delivery_days ≤ days_until_deadline`
3. Если нет подходящих — берутся все котировки, сортировка по `delivery_days ASC`
4. Иначе сортировка по `price ASC`, при равенстве цены — по `delivery_days ASC`
5. Применяется наценка: `final_price = price × (1 + MARGIN_PERCENT/100)`
6. Победитель UPSERT-ится в `winners`, обновление только если `new_final_price < current_final_price`

## Запуск

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск
python -m cmd.main

# Или через uvicorn
uvicorn cmd.main:app --host 0.0.0.0 --port 8080
```

## Логика закрытия заявки

После каждой котировки проверяется, все ли позиции RFQ имеют победителя. Если да — генерируется отчет и публикуется сообщение в `report_ready`.

Формат `report_ready`:

```json
{
  "rfq_id": "42",
  "file_key": "reports/rfq_42.xlsx"
}
```

## Формат Excel

- Лист: `КП #{rfq_id}`
- Колонки: №, Наименование МТР, Техобозначение, Материал, ГОСТ/ТУ, ТТ-ОЛ, Ед.изм, Кол-во, Срок поставки, Место назначения, РКД, Условия оплаты, **Цена без НДС**, **Email поставщика**, **Срок (дней)**, **Адрес самовывоза**, **Поставщик**
- Победители: зелёный фон (`#E8F5E9`)
- Без котировок: жёлтый фон (`#FFF9C4`)
- Последняя строка: `SUM(final_price)` — итоговая сумма

## Миграции БД

Создать таблицы перед запуском (добавить в общий скрипт миграций):

```sql
CREATE TABLE IF NOT EXISTS quotes (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    supplier_email VARCHAR(255),
    price NUMERIC(12,2) NOT NULL,
    delivery_days INTEGER,
    pickup_address TEXT,
    source VARCHAR(32),
    received_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(item_id, supplier_id)
);

CREATE TABLE IF NOT EXISTS winners (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL UNIQUE REFERENCES items(id),
    quote_id INTEGER NOT NULL REFERENCES quotes(id),
    final_price NUMERIC(12,2) NOT NULL,
    margin_pct NUMERIC(5,2) NOT NULL,
    chosen_at TIMESTAMP DEFAULT NOW()
);
```