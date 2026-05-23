# Multi-Service Tender Platform

Полная система для автоматизации тендеров:

## 🚀 Быстрый старт

### 1. Получите VK токен (обязательно)

1. Создайте сообщество ВКонтакте: https://vk.com/create
2. Перейдите в **Управление сообществом** → **Работа с API** → **Ключи доступа**
3. Создайте **Открытый ключ** (Server key)
4. Скопируйте `Service token` — это и есть `VK_GROUP_TOKEN`
5. Запомните `Group ID` — это `VK_GROUP_ID` (число)

### 2. Настройка переменных

```bash
cp .env.example .env
# Отредактировать .env:
# - VK_GROUP_TOKEN (получен на шаге 1)
# - VK_GROUP_ID (ID вашего сообщества)
# - YANDEX_XML_USER / YANDEX_XML_KEY (опционально, для поиска поставщиков)
#   Без этих ключей supplier-finder не будет искать поставщиков!
# - OPENROUTER_API_KEY (опционально, для AI ответов)
```

**Внимание:**
- `YANDEX_XML_USER` и `YANDEX_XML_KEY` **обязательны** для работы supplier-finder. Получите на https://xml.yandex.ru/
- Без них пайплайн остановится на этапе поиска поставщиков
- Можно временно добавить поставщиков вручную через VK Bot (`➕ поставщик`)

## Сервисы

| Service | Язык | Port | Назначение |
|---------|------|------|-----------|
| **communication-service** | Go | 8080 | IMAP → парсинг → SMTP → supplier_found |
| **supplier-finder** | Python | — | Поиск поставщиков (Яндекс.XML / DuckDuckGo) |
| **report-service** | Python | 8081 | Агрегация котировок → Excel |
| **vk-bot** | Python | — | Long Poll VK Bot: заявки, статусы, отчёты |
| **postgres** | — | 5432 | База данных |
| **redis** | — | 6379 | Streams + pub/sub |
| **smtp** (MailHog) | — | 1025 | SMTP для разработки |
| **imap** (MailDev) | — | 993 | IMAP для разработки |

## 📊 Архитектура

```
              ┌─────────────────────────────────────────────────────┐
              │             Redis Streams / PubSub                 │
              │  new_rfq → suppliers_found → quote_received       │
              └───────────────────┬───────────────────────────────┘
                                  │
         ┌────────────────────────┼─────────────────────────────┐
         │                        ▼                             ▼
         ▼            ┌──────────────────┐       ┌──────────────────┐
┌──────────────────┐   │   supplier-      │       │ communication    │
│     vk-bot       │──▶│   finder         │──▶    │   service        │
│   (Python)       │   │   (Python)       │       │   (Go)           │
│                  │   │                  │       │                  │
│ Excel upload     │   │ Яндекс.XML /     │       │ IMAP → parse →   │
│ Status commands  │   │ DuckDuckGo       │       │ SMTP → send RFQ  │
│                  │   │ → save suppliers │       │                  │
└──────────────────┘   └──────────────────┘       └──────────────────┘
                                                       │
                                                       ▼
                                            ┌──────────────────┐
                                            │   report-        │
                                            │   service        │
                                            │   (Python)       │
                                            │                  │
                                            │ Aggregate quotes │
                                            │ Generate Excel   │
                                            │ report_ready     │
                                            └────────┬─────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │     vk-bot       │
                                            │   (receive file) │
                                            └──────────────────┘
```
              ┌─────────────────────────────────────────────────────┐
              │             Redis Streams / PubSub                 │
              │  new_rfq → suppliers_found → quote_received       │
              └───────────────────┬───────────────────────────────┘
                                  │
         ┌────────────────────────┼─────────────────────────────┐
         │                        ▼                             ▼
         ▼            ┌──────────────────┐       ┌──────────────────┐
┌──────────────────┐   │   supplier-      │       │ communication    │
│     vk-bot       │──▶│   finder         │──▶    │   service        │
│   (Python)       │   │   (Python)       │       │   (Go)           │
│                  │   │                  │       │                  │
│ Excel upload     │   │ Яндекс.XML /     │       │ IMAP → parse →   │
│ Status commands  │   │ DuckDuckGo       │       │ SMTP → send RFQ  │
│                  │   │ → save suppliers │       │                  │
└──────────────────┘   └──────────────────┘       └──────────────────┘
                                                       │
                                                       ▼
                                            ┌──────────────────┐
                                            │   report-        │
                                            │   service        │
                                            │   (Python)       │
                                            │                  │
                                            │ Aggregate quotes │
                                            │ Generate Excel   │
                                            │ report_ready     │
                                            └────────┬─────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │     vk-bot       │
                                            │   (receive file) │
                                            └──────────────────┘
```

## 📁 Структура проекта

```
.
├── communication-service/   # Go сервис (email)
├── supplier-finder/         # Python сервис (поиск поставщиков)
├── report-service/         # Python сервис (отчёты)
├── vk-bot/                 # VK бот
├── migrations/             # Общие миграции БД
├── docker-compose.yml
├── Makefile
└── README.md
```

## 🗄️ Миграции БД

Автоматически применяются при первом запуске PostgreSQL контейнера из папки `migrations/`:

- `communication-service/migrations/` — базовые таблицы (items, suppliers, rfq_sends, supplier_threads, supplier_search_results, search_log, rfq_requests)
- `report-service/` — quotes, winners (применяются через root migrations)
- `migrations/004_vk_bot_tables.sql` — vk_users, quote_responses, created_by_vk column

**Примечание:** Таблицы `suppliers`, `supplier_emails`, `supplier_search_results`, `search_log` создаются в communication-service миграциях и используются всеми сервисами.

## ⚙️ Конфигурация

### Переменные окружения

| Переменная | Обязательная | Описание |
|-----------|-------------|----------|
| `VK_GROUP_TOKEN` | да | Токен группы ВКонтакте |
| `VK_GROUP_ID` | да | ID группы |
| `DB_DSN` | да | PostgreSQL DSN |
| `REDIS_URL` | да | Redis URL |
| `REPORT_SERVICE_URL` | да | URL report-service |
| `OPENROUTER_API_KEY` | нет | OpenRouter API key (для ответов на вопросы) |
| `OPENROUTER_MODEL` | нет | Модель AI (по умолчанию openai/gpt-5.2) |
| `YANDEX_XML_USER` | нет | Логин Яндекс.XML (для supplier-finder) |
| `YANDEX_XML_KEY` | нет | Ключ Яндекс.XML API |
| `ADMIN_VK_IDS` | нет | Список admin VK IDs через запятую |

### Email (SMTP/IMAP)

Для development используются **MailHog** (SMTP) и **MailDev** (IMAP) — они запускаются в docker-compose автоматически.

| Переменная | Значение по умолчанию | Описание |
|-----------|----------------------|----------|
| `SMTP_HOST` | `smtp` | Хост SMTP (внутренний DNS Docker) |
| `SMTP_PORT` | `1025` | Порт SMTP |
| `SMTP_USER` | пусто | Логин (не требуется дляMailHog) |
| `SMTP_PASS` | пусто | Пароль |
| `SMTP_FROM` | `noreply@tender.local` | Отправитель писем |
| `IMAP_HOST` | `imap` | Хост IMAP |
| `IMAP_PORT` | `993` | Порт IMAP |
| `IMAP_USER` | `test@localhost` | Пользователь IMAP |
| `IMAP_PASS` | `test` | Пароль IMAP |
| `IMAP_FOLDER` | `INBOX` | Папка для чтения |
| `IMAP_POLL_INTERVAL` | `300s` | Интервал проверки |
| `SMTP_DELAY` | `1s` | Задержка между отправками |
| `MAX_EMAILS_PER_ITEM` | `5` | Лимит писем на позицию |

## 🔧 Команды Make

| Команда | Описание |
|---------|---------|
| `make up` | Запустить все сервисы |
| `make down` | Остановить все сервисы |
| `make build` | Собрать Docker образы |
| `make logs` | Логи всех сервисов |
| `make logs-comm` | Логи communication-service |
| `make logs-report` | Логи report-service |
| `make logs-vk` | Логи vk-bot |
| `make logs-supplier` | Логи supplier-finder |
| `make ps` | Статус контейнеров |
| `make health` | Проверка health-эндпоинтов |
| `make db-shell` | Подключиться к PostgreSQL |
| `make redis-cli` | Подключиться к Redis CLI |
| `make clean` | Удалить все контейнеры и volumes |

## 📝 API Reference

### Report Service

```
GET /health
→ {"status": "ok", "db": "ok", "redis": "ok"}

GET /report/{rfq_id}/status
→ {
    "rfq_id": 42,
    "total": 50,
    "quoted": 38,
    "winners": 35,
    "ready": false
  }

POST /report/{rfq_id}/generate
→ application/vnd.openxmlformats-officedocument.spreadsheetml.sheet

GET /report/{rfq_id}/file
→ скачать существующий файл
```

### Communication Service

```
GET /health
→ {"status": "ok", "db": "ok", "redis": "ok"}
```

## 🔄 Workflow (полный цикл)

1. **Пользователь** загружает Excel через VK бота
2. **vk-bot** парсит файл → сохраняет items в PostgreSQL → публикует `new_rfq` в Redis
3. **supplier-finder** читает `new_rfq` → ищет поставщиков через Яндекс.XML / DuckDuckGo → сохраняет в БД → публикует `suppliers_found`
4. **communication-service** читает `suppliers_found` → отправляет email (SMTP) → логирует `rfq_sends`
5. **Поставщик** отвечает на email
6. **communication-service** читает IMAP:
   - Если вопрос → OpenRouter → отправка ответа
   - Если котировка → публикует `quote_received`
7. **report-service** читает `quote_received` → сохраняет котировку → выбирает победителя → проверяет завершённость RFQ
8. **report-service** генерирует Excel → сохраняет в volume → публикует `report_ready`
9. **vk-bot** читает `report_ready` → загружает файл из volume → отправляет пользователю через VK Documents API

## 🧪 Тестирование полного цикла

### Шаг 1: Запуск системы

```bash
make build
make up
make health  # Должны увидеть ok у communication-service и report-service
```

### Шаг 2: Проверка логов supplier-finder

```bash
make logs-supplier
```

**Ожидаем увидеть:**
```
[DB] Подключен
[Redis] Подключен
[Stream] Создана группа 'supplier-finder-group' для stream 'new_rfq'
[Consumer] Старт: stream=new_rfq, group=supplier-finder-group
```

Если видите ошибки **Yandex XML credentials not set** — добавьте `YANDEX_XML_USER` и `YANDEX_XML_KEY` в `.env` и перезапустите: `make restart supplier-finder`

### Шаг 3: Создание заявки в VK

1. Откройте VK Messenger
2. Найдите ваше сообщество по `VK_GROUP_ID`
3. Напишите боту: `начать`
4. Бот ответит приветствием
5. Отправьте `📝 Новая заявка` (или текстом "новая заявка")
6. Бот попросит загрузить Excel

### Шаг 4: Подготовка тестового Excel

Создайте файл `test.xlsx`:

| Наименование МТР | Количество | Срок поставки | Техобозначение | ГОСТ/ТУ | Ед.изм | Место назначения | Условия оплаты |
|-----------------|------------|---------------|----------------|---------|--------|------------------|---------------|
| Кабель контрольный КПСнг(А)-F 4х2х0.75 | 100 | 20.05.2026 | КПСнг-Ф | ГОСТ 18690 | м | Москва | 100% предоплата |
| Круг стальной 40 | 50 | 25.05.2026 | Сталь 40 | ГОСТ 1050-88 | кг | Санкт-Петербург | 50% предоплата |

Отправьте файл в диалог с ботом.

**Ожидаемый ответ бота:**
```
Найдено 2 позиций:

1. Кабель контрольный КПСнг(А)-F... — 100 м — 20.05.2026
2. Круг стальной 40 — 50 кг — 25.05.2026

Город: Москва
Бюджет: не указан

Подтвердить создание заявки?
[✅ Подтвердить] [❌ Отмена]
```

### Шаг 5: Подтверждение заявки

Нажмите `✅ Подтвердить` (или отправьте "да")

**Ожидаемый ответ:**
```
✅ Заявка #1 создана!

Начинается поиск поставщиков...
Вы получите уведомление, когда котировки будут собраны.
```

### Шаг 6: Проверка базы данных

```bash
make db-shell
```

```sql
-- Проверить заявку
SELECT * FROM rfq_requests ORDER BY id DESC LIMIT 1;
-- Должна быть запись с created_by_vk = ваш_vk_id

-- Проверить позиции
SELECT * FROM items WHERE rfq_id = 1;

-- Проверить результаты поиска (если Yandex ключи заданы)
SELECT * FROM supplier_search_results WHERE item_id IN (1,2);
-- Должны быть записи с поставщиками

-- Проверить emails
SELECT s.domain, array_agg(se.email) 
FROM suppliers s 
JOIN supplier_emails se ON se.supplier_id = s.id 
GROUP BY s.domain;
```

### Проверка Health Supplier-Finder

```bash
curl http://localhost:8000/health
# Должно вернуть: {"status":"ok","db":"ok","redis":"ok"}
```

---

## ⚠️ **Без Yandex XML ключей**

Supplier-finder **умеет fallback на DuckDuckGo** (без ключей), но:

- DuckDuckGo медленнее
- Меньше результатов
- Может блокироваться капчей

**Если не находит поставщиков:**
1. Проверьте логи: `make logs-supplier`
2. Ищите: `Yandex XML не настроен → DuckDuckGo` или `Yandex: ... URLs`
3. Если DuckDuckGo тоже не находит → вручную добавляйте через VK Bot (`➕ поставщик`)

### Проверка Health Supplier-Finder

```bash
curl http://localhost:8000/health
# Должно вернуть: {"status":"ok","db":"ok","redis":"ok"}
```

---

## ⚠️ **Без Yandex XML ключей**

Supplier-finder **умеет fallback на DuckDuckGo** (без ключей), но:

- DuckDuckGo медленнее
- Меньше результатов
- Может блокироваться капчей

**Если не находит поставщиков:**
1. Проверьте логи: `make logs-supplier`
2. Ищите: `Yandex XML не настроен → DuckDuckGo` или `Yandex: ... URLs`
3. Если DuckDuckGo тоже не находит → вручную добавляйте через VK Bot (`➕ поставщик`)

### Шаг 7: Проверка отправки писем

Откройте **MailHog UI**: http://localhost:8025

Должны видны **исходящие письма**:
- От: `noreply@tender.local`
- Кому: `info@...`, `sales@...` (emails от найдённых поставщиков)
- Тема: `Запрос коммерческого предложения #1`

**Если писем нет:**
- Проверьте логи `communication-service`: `make logs-comm`
- Ищите: `RFQ email sent successfully` или ошибки

### Шаг 8: Имитация ответа поставщика

Откройте **MailDev UI**: http://localhost:1080

1. Найдите одно из отправленных писем (от communication-service)
2. Нажмите **Reply** (или перешлите на test@localhost)
3. В теме оставьте `Re: Запрос коммерческого предложения #1`
4. В теле письма напишите цену:

```
Цена: 1850 руб за метр
Срок поставки: 14 дней
Самовывоз: Москва, Складовская ул. 1
```

5. Отправьте письмо

### Шаг 9: Проверка обработки котировки

```bash
make logs-comm  # следим за IMAP listener
```

**Ожидаем:**
```
Quote received and published
```

```bash
make logs-report  # следим за quote worker
```

**Ожидаем:**
```
Quote saved: item=1, supplier=..., price=1850.0
Winner updated: item=1, quote_id=..., final_price=2127.5
RFQ 1 not complete yet  # или "Report ready published" если все позиции имеют Winners
```

### Шаг 10: Проверка generation отчёта

Если все позиции имеют победителей:

```bash
make logs-report
```

Должно быть:
```
Report ready published: rfq_id=1
```

### Шаг 11: Получение отчёта в VK

Через несколько секунд VK Bot пришлёт вам документ:

```
Отчёт по заявке #1
📄 report_1.xlsx
```

### Шаг 12: Проверка файла Excel

Откройте файл. Проверьте:
- Победители выделены **зелёным** фоном
- Позиции без котировок — **жёлтым**
- Итоговая сумма внизу: `SUM(final_price)`

---

## 🐛 Возможные проблемы

| Проблема | Причина | Решение |
|----------|---------|---------|
| supplier-finder не находит поставщиков | Нет Yandex XML ключей | Добавить `YANDEX_XML_USER` и `YANDEX_XML_KEY` в `.env`, `make restart supplier-finder` |
| Письма не отправляются | SMTP host不正确 | Проверить `docker-compose ps`, должен быть `mailhog-smtp` Up |
| IMAP не читает письма | MailDev down | `docker-compose logs imap` |
| Нет котировок в report-service | communication-service не обработал письмо | Проверить `make logs-comm`, искать `Quote received` |
| Отчёт не генерируется | Не все позиции имеют победителей | Нужно больше котировок (отправить ответы от нескольких поставщиков) |
| VK бот не отвечает | Нет VK токена или токен неверный | Проверить `make logs-vk`, искать `auth` ошибки |

```bash
# Go
cd communication-service
go vet ./...
go test ./...

# Python (pre-commit)
cd report-service
pip install -r requirements.txt
black . && isort . && flake8 . && mypy .

cd ../vk-bot
pip install -r requirements.txt
black . && isort . && flake8 . && mypy .

cd ../supplier-finder
pip install -r requirements.txt
black . && isort . && flake8 . && mypy .
```

## 📈 Мониторинг (планы)

- Prometheus /metrics на каждом сервисе
- Логи в JSON (structured)
- Grafana dashboard
- Alert on service down

---

**Готово к запуску:** `make up`
