"""
supplier-finder — точка входа с использованием Redis Streams.

Схема:
  - Читает stream 'new_rfq' через XREADGROUP
  - Группа: 'supplier-finder-group'
  - Подтверждает (XACK) только после успешной обработки и сохранения в БД
  - Публикует результаты в stream 'suppliers_found'
"""
import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any

import asyncpg
import redis.asyncio as redis
from dotenv import load_dotenv

from models.events import NewItemEvent, SuppliersFoundEvent
from services.finder import process_item

load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Конфигурация
DB_DSN = os.getenv("DB_DSN", "postgres://postgres:postgres@localhost:5432/procurement")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Streams
STREAM_RFQ = os.getenv("STREAM_RFQ", "new_rfq")                    # входящий
STREAM_RESULTS = os.getenv("STREAM_RESULTS", "suppliers_found")    # исходящий

# Группа потребителя
GROUP_NAME = os.getenv("RFQ_GROUP_NAME", "supplier-finder-group")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", f"supplier-finder-{os.getpid()}")

# Параметры потребления
BLOCK_MS = int(os.getenv("STREAM_BLOCK_MS", "2000"))     # 2 секунды
BATCH_SIZE = int(os.getenv("STREAM_BATCH_SIZE", "10"))   # сообщений за раз

# Конкурентность обработки внутри consumer
MAX_CONCURRENT_ITEMS = int(os.getenv("ITEM_CONCURRENCY", "3"))


async def ensure_stream_and_group(redis_client: redis.Redis, stream: str, group: str):
    """
    Идемпотентное создание stream и consumer group.
    Если stream не существует — создаётся через mkstream.
    Если группа уже есть — просто продолжаем.
    """
    try:
        await redis_client.xgroup_create(
            stream, group, id="0", mkstream=True
        )
        logger.info(f"[Stream] Создана группа '{group}' для stream '{stream}'")
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"[Stream] Группа '{group}' уже существует")
        else:
            logger.warning(f"[Stream] Ошибка при создании группы: {e}")


async def publish_result(redis_client: redis.Redis, event: SuppliersFoundEvent):
    """
    Публикует результат поиска в stream 'suppliers_found'.
    """
    data = {
        "item_id": str(event.item_id),
        "item_name": event.item_name,
        "emails_count": str(event.emails_count),
        "suppliers": json.dumps(event.suppliers, ensure_ascii=False),
    }
    
    msg_id = await redis_client.xadd(STREAM_RESULTS, data)
    logger.info(f"[Stream] → {STREAM_RESULTS} [{msg_id}] item_id={event.item_id}, emails={event.emails_count}")
    return msg_id


async def handle_rfq_message(
    redis_client: redis.Redis,
    db_pool: asyncpg.Pool,
    stream_name: str,
    group: str,
    msg_id: str,
    data: dict,
):
    """
    Обработка одного сообщения из new_rfq.
    """
    logger.info(f"[Handler] Обработка {msg_id}: {data}")
    
    try:
        # Парсим входящие данные
        rfq_id = data.get(b"rfq_id", data.get("rfq_id"))
        items_json = data.get(b"items", data.get("items", "[]"))
        
        if isinstance(items_json, bytes):
            items_json = items_json.decode()
        
        items = json.loads(items_json)
        
        if not items:
            logger.warning(f"[Handler] Нет items в сообщении {msg_id}")
            await redis_client.xack(stream_name, group, msg_id)
            return
        
        # Обрабатываем каждый item в позиции (с конкурентностью)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_ITEMS)
        
        async def process_one(item: dict):
            async with semaphore:
                # vk-bot отправляет "num", а не "id" — приводим к совместимости
                item_id = item.get("id") or item.get("num")
                if not item_id:
                    logger.warning(f"[Handler] Item без ID: {item}")
                    return
                
                event = NewItemEvent(
                    id=item_id,
                    name=item.get("name", ""),
                    tech_code=item.get("tech_code", ""),
                    gost=item.get("gost", ""),
                    location=item.get("location", ""),
                    region=item.get("region", 1),
                )
                await process_item(event, db_pool, redis_client)
        
        tasks = [process_one(item) for item in items]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Подтверждаем успешную обработку ВСЕХ items в сообщении
        await redis_client.xack(stream_name, group, msg_id)
        logger.info(f"[Handler] ✅ Обработан и подтверждён {msg_id}")
        
    except Exception as e:
        logger.error(f"[Handler] ❌ Ошибка обработки {msg_id}: {e}", exc_info=True)
        # НЕ вызываем xack — сообщение останется в PEL
        # При перезапуске будет обработано снова


async def consume_rfq(
    redis_client: redis.Redis,
    db_pool: asyncpg.Pool,
    shutdown: asyncio.Event,
):
    """
    Основной цикл потребления сообщений из new_rfq.
    """
    stream = STREAM_RFQ
    group = GROUP_NAME
    
    # Создаём stream и группу
    await ensure_stream_and_group(redis_client, stream, group)
    
    logger.info(f"[Consumer] Старт: stream={stream}, group={group}, consumer={CONSUMER_NAME}")
    
    while not shutdown.is_set():
        try:
            # Читаем сообщения из группы
            result = await redis_client.xreadgroup(
                group,
                CONSUMER_NAME,
                {stream: ">"},      # ">" — читаем только новые сообщения
                count=BATCH_SIZE,
                block=BLOCK_MS,
            )
            
            if not result:
                # Нет сообщений
                continue
            
            # result: [(stream_name, [(msg_id, data), ...]), ...]
            for stream_name, entries in result:
                for msg_id, data in entries:
                    if shutdown.is_set():
                        break
                    
                    # Запускаем обработку в фоне, не блокируя чтение
                    asyncio.create_task(
                        handle_rfq_message(
                            redis_client, db_pool, stream_name, group, msg_id, data
                        )
                    )
                    
        except redis.ResponseError as e:
            logger.error(f"[Consumer] Redis ошибка: {e}")
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[Consumer] Неожиданная ошибка: {e}", exc_info=True)
            await asyncio.sleep(1)
    
    logger.info("[Consumer] Остановлен")


async def cleanup_pending(redis_client: redis.Redis):
    """
    Опционально: просмотр зависших сообщений в PEL.
    Можно расширить для автоматической обработки dead-letter.
    """
    stream = STREAM_RFQ
    group = GROUP_NAME
    
    try:
        pending = await redis_client.xpending_range(stream, group, "-", "+", 100)
        if pending:
            logger.warning(f"[Pending] Найдено {len(pending)} зависших сообщений")
            for entry in pending:
                logger.warning(f"  - {entry['message_id']} (consumer: {entry['consumer']}, idle: {entry['idle']}ms)")
    except Exception as e:
        logger.debug(f"[Pending] Ошибка проверки PEL: {e}")


async def main():
    logger.info("🚀 [Supplier-Finder] Запуск с Redis Streams")
    
    # Подключение к PostgreSQL
    logger.info("[DB] Подключение...")
    db_pool = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=10)
    logger.info("[DB] ✅ Подключен")
    
    # Подключение к Redis
    logger.info("[Redis] Подключение...")
    redis_client = redis.from_url(REDIS_URL, decode_responses=False)
    await redis_client.ping()
    logger.info("[Redis] ✅ Подключен")
    
    # Миграции не требуются — таблицы созданы communication-service
    
    # Показываем статистику PEL (опционально)
    await cleanup_pending(redis_client)
    
    shutdown = asyncio.Event()
    
    # Graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)
    
    # Запускаем consumer в отдельной задаче
    consumer_task = asyncio.create_task(consume_rfq(redis_client, db_pool, shutdown))
    
    # Запускаем API сервер (опционально, для health checks)
    try:
        import uvicorn
        from internal.api import app as fastapi_app
        
        config = uvicorn.Config(
            fastapi_app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
        server = uvicorn.Server(config)
        
        # Запускаем API и consumer одновременно
        await asyncio.gather(
            server.serve(),
            consumer_task
        )
    except ImportError:
        # Если uvicorn не установлен, запускаем только consumer
        logger.warning("FastAPI/uvicorn не установлен, health check недоступен")
        await consumer_task
    
    logger.info("[Shutdown] Соединения закрыты")
    await db_pool.close()
    await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())