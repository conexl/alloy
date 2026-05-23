# VK Bot Service

## Назначение

VK бот для участия в тендерах:
- Создание заявок через загрузку Excel
- Отслеживание статуса котировок
- Получение итоговых отчётов
- Добавление поставщиков вручную

## Стек

- Python 3.12
- vkbottle 4.x — асинхронный фреймворк для VK Bot API (Long Poll)
- pandas + openpyxl — парсинг Excel
- httpx — HTTP клиент
- asyncpg — PostgreSQL
- redis-py — Redis Streams
- pydantic-settings — конфигурация
- loguru — логирование

## Переменные окружения

```bash
VK_GROUP_TOKEN=your_group_token
VK_GROUP_ID=12345678
VK_SECRET=          # опционально для callback
VK_CONFIRMATION=   # опционально

DB_DSN=postgresql://postgres:postgres@localhost:5432/tender?sslmode=disable
REDIS_URL=redis://localhost:6379
REPORT_SERVICE_URL=http://report-service:8081

ADMIN_VK_IDS=123456789,987654321
```

## Архитектура

```
vk-bot/
├── cmd/
│   └── main.py           # Точка входа (Long Poll)
├── internal/
│   ├── config/
│   │   └── config.py     # Конфигурация
│   ├── domain/
│   │   ├── models.py     # User, RFQ
│   │   └── repository.py # Интерфейсы
│   ├── repository/
│   │   ├── postgres.py   # БД (vk_users, rfq_requests, items)
│   │   └── redis.py      # Redis (new_rfq, report_ready, quote_received)
│   ├── services/
│   │   └── excel_parser.py  # Парсинг Excel
│   ├── handlers/
│   │   └── bot_handlers.py  # Обработчики сообщений
│   ├── workers/
│   │   └── report_ready.py  # Слушает report_ready, шлёт файлы
│   ├── keyboards/
│   │   └── keyboards.py     # VK клавиатуры
│   └── app/
│       └── app.py           # Lifespan, DI
├── Dockerfile
└── requirements.txt
```

## База данных

### vk_users

```sql
CREATE TABLE IF NOT EXISTS vk_users (
    vk_id BIGINT PRIMARY KEY,
    vk_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### rfq_requests (добавляем created_by_vk)

```sql
ALTER TABLE rfq_requests 
ADD COLUMN IF NOT EXISTS created_by_vk BIGINT REFERENCES vk_users(vk_id);
```

## Команды

VK бот реагирует на текстовые команды (не slash):

| Триггер | Действие |
|---------|----------|
| начать, старт, start, привет, помощь | Приветствие + меню |
| статус | Статус последней заявки |
| отчёт, отчет | Скачать отчёт |
| новая заявка, заявка | Загрузить Excel |
| поставщик | Добавить поставщика вручную |

## Сценарии

### 1. Создание заявки

1. Пользователь: "новая заявка"
2. Бот: "Пришлите Excel-файл"
3. Пользователь: прикрепляет `.xlsx`
4. Бот парсит, показывает превью (первые 5 позиций)
5. Кнопки: ✅ Подтвердить / ❌ Отмена
6. При подтверждении: INSERT в БД + `xadd("new_rfq")`
7. `communication-service` находит поставщиков, публикует `supplier_found`

### 2. Статус заявки

1. Пользователь: "статус"
2. Бот показывает:
   ```
   Заявка #42
   Позиций: 50
   С котировками: 38
   Победителей: 35
   Статус: ⏳ В работе
   ```
3. Кнопки: [🔄 Обновить] [📥 Получить отчёт]

### 3. Получение отчёта

1. Пользователь: "отчёт"
2. Бот вызывает `POST /report/{rfq_id}/generate`
3. Получает xlsx, загружает через VK Documents API
4. Отправляет как вложение

### 4. Добавление поставщика

1. Пользователь: "поставщик"
2. Бот: "Отправьте: <supplier_id> <email>"
3. Пользователь: `12345 vendor@example.com`
4. Бот сохраняет в `suppliers` (вручную)

## Клавиатуры VK

VK использует `Keyboard` (прикреплённая к полю ввода):

```python
Keyboard(one_time=False, inline=False)
    .add(Text("📝 Новая заявка"), color=ButtonColor.PRIMARY)
    .add(Text("📊 Статус"), color=ButtonColor.SECONDARY)
```

Inline кнопки (в самом сообщении) не поддерживаются в Long Poll.

## Отправка файлов

VK не позволяет отправить файл напрямую из байтов:

1. `docs.getUploadServer` → получить `upload_url`
2. `POST upload_url` с multipart/form-data
3. `docs.save` → получить `owner_id` и `id`
4. `messages.send(attachment=f"doc{owner_id}_{id}")`

## Запуск

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск (Long Poll)
python -m cmd.main

# Или через FastAPI (health)
uvicorn cmd.main:app --host 0.0.0.0 --port 8082
```

## Docker

```yaml
vk-bot:
  build: ./vk-bot
  environment:
    VK_GROUP_TOKEN: ${VK_GROUP_TOKEN}
    DB_DSN: postgres://postgres:postgres@postgres:5432/tender?sslmode=disable
    REDIS_URL: redis://redis:6379
    REPORT_SERVICE_URL: http://report-service:8081
  depends_on:
    - postgres
    - redis
```

## Замечания

- Long Poll не требует публичного URL
- Ограничение: 4096 символов в сообщении
- Кнопки прикрепляются к полю ввода (не inline)
- Необходимо обрабатывать rate limits VK API

## TODO

- [ ] Webhook + Callback API (как альтернатива Long Poll)
- [ ] Состояния (FSM) для многошаговых диалогов
- [ ] Отправка сообщений "поставщик найден" прямо в чат
- [ ] Админ-панель (список пользователей, RFQ)
- [ ] Поддержка нескольких заявок на пользователя
- [ ] Интеграция с report-service через HTTP вместо Redis Streams