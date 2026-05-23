"""
Оркестратор поиска поставщиков:
  1. Строит запрос из полей МТР
  2. Ищет URL (Yandex XML → DuckDuckGo fallback)
  3. Параллельно парсит контакты с ограничением
  4. Сохраняет в PostgreSQL
  5. Публикует результат в Redis Stream 'suppliers_found'
"""
import asyncio
import json
import logging
import os
from urllib.parse import urlparse

import asyncpg
from redis.asyncio import Redis

from models.events import NewItemEvent, SuppliersFoundEvent
from services.yandex_xml import search_yandex, SearchResult as YandexResult
from services.duckduckgo_search import (
    configure_proxies,
    search_duckduckgo,
    SearchResult as DDGResult,
)
from services.contact_parser import parse_contacts, ParseResult
from utils.query_builder import build_query_set
from utils.db import (
    save_contact_result,
    save_search_log,
    get_supplier_emails,
    already_searched,
    get_cached_supplier,
    touch_supplier,
)

logger = logging.getLogger(__name__)

YANDEX_USER = os.getenv("YANDEX_XML_USER")
YANDEX_KEY = os.getenv("YANDEX_XML_KEY")

MAX_URLS = int(os.getenv("MAX_URLS_PER_ITEM", "8"))
MAX_CONCURRENT_PARSERS = int(os.getenv("MAX_CONCURRENT_PARSERS", "4"))

STREAM_RESULTS = os.getenv("STREAM_RESULTS", "suppliers_found")

# ── DuckDuckGo proxy rotation ─────────────────────────────────────────
_DDG_PROXY_USER = os.getenv("DDG_PROXY_USER", "")
_DDG_PROXY_PASS = os.getenv("DDG_PROXY_PASS", "")
_DDG_PROXY_LIST_RAW = os.getenv("DDG_PROXY_LIST", "")

if _DDG_PROXY_USER and _DDG_PROXY_PASS and _DDG_PROXY_LIST_RAW:
    hosts = [h.strip() for h in _DDG_PROXY_LIST_RAW.split(",") if h.strip()]
    proxies = [f"http://{_DDG_PROXY_USER}:{_DDG_PROXY_PASS}@{h}" for h in hosts]
    configure_proxies(proxies)
    logger.info(f"[Finder] DDG прокси: {len(proxies)} шт.")
else:
    logger.info("[Finder] DDG прокси не настроены — прямой доступ")


# ---------------------------------------------------------------------------
# Поиск URL
# ---------------------------------------------------------------------------

async def _search_urls(query: str, region: int) -> tuple[list[str], str]:
    """
    Ищет сайты поставщиков.
    Приоритет: Yandex XML → DuckDuckGo.
    Возвращает (urls, engine_name).
    """
    if YANDEX_USER and YANDEX_KEY:
        try:
            results: list[YandexResult] = await search_yandex(
                query, YANDEX_USER, YANDEX_KEY, region=region, max_results=MAX_URLS
            )
            if results:
                urls = [r.url for r in results]
                logger.info(f"[Finder] Yandex: {len(urls)} URL для '{query}'")
                return urls, "yandex"
        except Exception as e:
            logger.warning(f"[Finder] Yandex XML ошибка: {e} → fallback DuckDuckGo")
    else:
        logger.info("[Finder] Yandex XML не настроен → DuckDuckGo")

    try:
        results: list[DDGResult] = await search_duckduckgo(query, max_results=MAX_URLS)
        urls = [r.url for r in results]
        logger.info(f"[Finder] DuckDuckGo: {len(urls)} URL для '{query}'")
        return urls, "duckduckgo"
    except Exception as e:
        logger.error(f"[Finder] DuckDuckGo ошибка: {e}")
        return [], "none"


# ---------------------------------------------------------------------------
# Публикация в Redis Stream
# ---------------------------------------------------------------------------

async def _publish_to_stream(redis_client: Redis, event: SuppliersFoundEvent) -> str:
    """
    Публикует результат поиска в stream 'suppliers_found'.
    Возвращает ID сообщения.
    """
    data = {
        "item_id": str(event.item_id),
        "item_name": event.item_name,
        "emails_count": str(event.emails_count),
        "suppliers": json.dumps(event.suppliers, ensure_ascii=False),
    }
    
    msg_id = await redis_client.xadd(STREAM_RESULTS, data)
    logger.info(f"[Finder] → Stream {STREAM_RESULTS} [{msg_id}] item_id={event.item_id}, emails={event.emails_count}")
    return msg_id


# ---------------------------------------------------------------------------
# Основной обработчик позиции МТР
# ---------------------------------------------------------------------------

async def process_item(event: NewItemEvent, db_pool: asyncpg.Pool, redis_client: Redis):
    """
    Полный цикл поиска поставщиков для одной позиции МТР.
    """
    logger.info(f"[Finder] Позиция #{event.id}: {event.name!r}")

    # Пропускаем если уже обрабатывали эту позицию
    async with db_pool.acquire() as conn:
        if await already_searched(conn, event.id):
            logger.info(f"[Finder] Позиция #{event.id} уже обработана")
            return

    # 1. Строим набор поисковых запросов (основной + fallback-и)
    qs = build_query_set(
        name=event.name,
        tech_code=event.tech_code,
        gost=event.gost,
        location=event.location,
    )
    region = event.region or qs.region
    query = qs.primary

    # 2. Ищем URL — пробуем основной запрос, затем fallback-и
    raw_urls: list[str] = []
    engine = "none"

    for candidate in [qs.primary] + qs.fallbacks:
        raw_urls, engine = await _search_urls(candidate, region)
        if raw_urls:
            if candidate != qs.primary:
                logger.info(f"[Finder] Fallback запрос сработал: {candidate!r}")
                query = candidate
            break

    urls = list(dict.fromkeys(raw_urls))[:MAX_URLS]

    if not urls:
        logger.warning(f"[Finder] URL не найдены для позиции #{event.id} (все запросы исчерпаны)")
        async with db_pool.acquire() as conn:
            await save_search_log(conn, event.id, query, engine, 0, 0)
        return

    # 3. Параллельный парсинг контактов
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PARSERS)

    async def _parse(url: str) -> ParseResult:
        async with semaphore:
            return await parse_contacts(url)

    # 3а. Проверяем кэш доменов — не парсим то что уже знаем (30 дней)
    urls_to_parse: list[str] = []
    cached_suppliers: list[dict] = []

    async with db_pool.acquire() as conn:
        for url in urls:
            domain = urlparse(url).netloc.removeprefix("www.")
            cached = await get_cached_supplier(conn, domain)
            if cached:
                logger.info(f"[Finder] Кэш: {domain} ({len(cached['emails'])} email)")
                cached_suppliers.append(cached)
                # Связываем кэшированного поставщика с текущей позицией
                await conn.execute(
                    """
                    INSERT INTO supplier_search_results (item_id, supplier_id, search_query, rank)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (item_id, supplier_id) DO NOTHING
                    """,
                    event.id, cached["supplier_id"], query, -1,
                )
                await touch_supplier(conn, cached["supplier_id"])
            else:
                urls_to_parse.append(url)

    logger.info(
        f"[Finder] Кэш: {len(cached_suppliers)} доменов, "
        f"парсинг: {len(urls_to_parse)} доменов"
    )

    # 3б. Парсим только незнакомые домены
    parse_results: list[ParseResult | BaseException] = []
    if urls_to_parse:
        logger.info(f"[Finder] Парсю {len(urls_to_parse)} сайтов (≤{MAX_CONCURRENT_PARSERS} параллельно)...")
        parse_results = await asyncio.gather(
            *[_parse(u) for u in urls_to_parse],
            return_exceptions=True,
        )

    # 4. Сохраняем в БД
    total_emails = 0
    suppliers_payload: list[dict] = []

    # Добавляем кэшированных поставщиков в payload сразу
    for cached in cached_suppliers:
        suppliers_payload.append({
            "supplier_id": cached["supplier_id"],
            "domain": cached.get("domain", "cached"),
            "emails": cached["emails"],
        })
        total_emails += len(cached["emails"])

    async with db_pool.acquire() as conn:
        for rank, res in enumerate(parse_results):
            if isinstance(res, BaseException):
                logger.warning(f"[Finder] Исключение при парсинге #{rank}: {res}")
                continue

            # Берём только лучшие email (топ-5 по score)
            best = res.best_emails(limit=5)
            if not best:
                continue

            contact_data = {
                "url": res.url,
                "domain": res.domain,
                "emails": [
                    {"email": h.email, "source": h.source_url, "page_type": h.page_type}
                    for h in best
                ],
                "checked_urls": res.checked_urls,
            }

            supplier_id, new_count = await save_contact_result(
                conn, event.id, contact_data, query, rank
            )
            total_emails += new_count

            if new_count > 0:
                emails = await get_supplier_emails(conn, supplier_id)
                suppliers_payload.append({
                    "supplier_id": supplier_id,
                    "domain": res.domain,
                    "emails": emails,
                })

        await save_search_log(conn, event.id, query, engine, len(urls), total_emails)

    logger.info(
        f"[Finder] Позиция #{event.id} готова: "
        f"{total_emails} email от {len(suppliers_payload)} поставщиков"
    )

    # 5. Публикуем результат в Redis Stream
    if suppliers_payload:
        out_event = SuppliersFoundEvent(
            item_id=event.id,
            item_name=event.name,
            emails_count=total_emails,
            suppliers=suppliers_payload,
        )
        await _publish_to_stream(redis_client, out_event)
    else:
        logger.warning(f"[Finder] Позиция #{event.id}: поставщики не найдены, событие не отправлено")