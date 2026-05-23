# Docker environments

## Development (default)

```bash
# Create .env file
cp .env.example .env
# Edit .env if needed (ANTHROPIC_API_KEY, etc.)
```

```bash
# Start all services
make up

# View logs
make logs

# Stop all services
make down

# Clean everything (WARNING: deletes data)
make clean
```

## Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Communication API | http://localhost:8080 | Email sending & IMAP listener |
| Report API | http://localhost:8081 | Quote aggregation & Excel reports |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Message streams |
| MailHog SMTP | localhost:1025 | SMTP server (captures emails) |
| MailHog UI | http://localhost:8025 | View captured emails |
| MailDev UI | http://localhost:1080 | Alternative mail UI |

## Health Checks

```bash
# All services
make health

# Individual
curl http://localhost:8080/health  # communication
curl http://localhost:8081/health  # report

# PostgreSQL
docker-compose exec postgres pg_isready -U postgres

# Redis
docker-compose exec redis redis-cli ping
```

## Data Volumes

- `postgres_data` — PostgreSQL data (persisted on host)
- `redis_data` — Redis AOF file (persisted)
- `report_data` — Generated Excel files (persisted, shared between containers)

## Migrations

Миграции для `report-service` автоматически применяются при первом запуске контейнера PostgreSQL (файлы в `./migrations`).

Для `communication-service` миграции уже должны быть в вашем основном проекте.

## Debugging Emails

Все письма, отправляемые через `communication-service` (SMTP), попадают в MailHog:
- Открой http://localhost:8025
- Здесь можно просмотреть все письма, Including HTML, headers

IMAP: почтовый ящик `test@localhost` (пароль `test`) доступен через:
- IMAP over SSL: `localhost:993`
- Web UI: http://localhost:1080

## Development Workflow

1. **Изменение кода в communication-service:**
   ```bash
   docker-compose up -d communication-service
   # Контейнер пересобирается автоматически (если есть bind mount в dev)
   ```

2. **Логи:**
   ```bash
   make logs-comm    # communication-service
   make logs-report  # report-service
   ```

3. **Перезапуск одного сервиса:**
   ```bash
   docker-compose restart communication-service
   ```

## Production Notes

Для production нужно:
1. Заменить MailHog/MailDev на реальный SMTP/IMAP сервер
2. Установить `ANTHROPIC_API_KEY` в .env
3. Настроить TLS certifictes
4. Использовать внешнюю БД (RDS, Cloud SQL)
5. Настроить логирование (JSON, Loki)
6. Добавить мониторинг (Prometheus metrics)
7. Настроить autoscaling (K8s)

## Troubleshooting

**Порт уже занят:**
```bash
lsof -ti:8080 | xargs kill -9
```

**Очистить всё:**
```bash
make clean
docker system prune -a
```

**Пересобирать образы:**
```bash
docker-compose build --no-cache
```