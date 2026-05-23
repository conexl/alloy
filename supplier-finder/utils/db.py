"""
Все операции с PostgreSQL для supplier-finder.
"""
from datetime import timedelta
import asyncpg
from models.events import ContactResult


async def get_or_create_supplier(conn: asyncpg.Connection, domain: str, source_url: str) -> int:
    """Возвращает id поставщика, создаёт если не существует."""
    row = await conn.fetchrow("SELECT id FROM suppliers WHERE domain = $1", domain)
    if row:
        return row["id"]
    return await conn.fetchval(
        """
        INSERT INTO suppliers (domain, source_url)
        VALUES ($1, $2)
        ON CONFLICT (domain) DO UPDATE SET source_url = EXCLUDED.source_url, updated_at = NOW()
        RETURNING id
        """,
        domain,
        source_url,
    )


async def save_contact_result(
    conn: asyncpg.Connection,
    item_id: int,
    result,  # Принимает как словарь, так и объект ContactResult
    search_query: str,
    rank: int,
) -> tuple[int, int]:
    """
    Сохраняет результат парсинга одного сайта.
    Возвращает (supplier_id, кол-во новых email).
    """
    # Поддержка как объектов, так и словарей
    if hasattr(result, 'domain'):
        # Это объект ContactResult
        domain = result.domain
        url = result.url
        emails = [{"email": e.email, "source": e.source, "page_type": e.page_type} for e in result.emails]
    else:
        # Это словарь
        domain = result["domain"]
        url = result["url"]
        emails = result["emails"]
    
    supplier_id = await get_or_create_supplier(conn, domain, url)

    new_emails = 0
    for email_info in emails:
        # Поддержка как словаря, так и объекта
        if isinstance(email_info, dict):
            email = email_info["email"]
            source = email_info["source"]
            page_type = email_info["page_type"]
        else:
            email = email_info.email
            source = email_info.source
            page_type = email_info.page_type
        
        exists = await conn.fetchval(
            "SELECT 1 FROM supplier_emails WHERE supplier_id = $1 AND email = $2",
            supplier_id,
            email,
        )
        if not exists:
            await conn.execute(
                """
                INSERT INTO supplier_emails (supplier_id, email, source_url, page_type)
                VALUES ($1, $2, $3, $4)
                """,
                supplier_id,
                email,
                source,
                page_type,
            )
            new_emails += 1

    await conn.execute(
        """
        INSERT INTO supplier_search_results (item_id, supplier_id, search_query, rank)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (item_id, supplier_id) DO NOTHING
        """,
        item_id,
        supplier_id,
        search_query,
        rank,
    )

    return supplier_id, new_emails


async def save_search_log(
    conn: asyncpg.Connection,
    item_id: int,
    query: str,
    engine: str,
    urls_found: int,
    emails_found: int,
):
    await conn.execute(
        """
        INSERT INTO search_log (item_id, query, engine, urls_found, emails_found)
        VALUES ($1, $2, $3, $4, $5)
        """,
        item_id,
        query,
        engine,
        urls_found,
        emails_found,
    )


async def get_supplier_emails(conn: asyncpg.Connection, supplier_id: int) -> list[str]:
    rows = await conn.fetch(
        "SELECT email FROM supplier_emails WHERE supplier_id = $1", supplier_id
    )
    return [r["email"] for r in rows]


async def already_searched(conn: asyncpg.Connection, item_id: int) -> bool:
    """Проверяет, был ли уже поиск по этой позиции."""
    row = await conn.fetchval(
        "SELECT 1 FROM search_log WHERE item_id = $1 LIMIT 1", item_id
    )
    return row is not None


DOMAIN_CACHE_DAYS = 30


async def get_cached_supplier(
    conn: asyncpg.Connection, domain: str
) -> dict | None:
    """
    Возвращает кэшированного поставщика если домен уже парсился
    в течение последних DOMAIN_CACHE_DAYS дней.

    Возвращает: {"supplier_id": int, "emails": list[str]} или None.
    """
    row = await conn.fetchrow(
        """
        SELECT id, updated_at
        FROM suppliers
        WHERE domain = $1
          AND updated_at > NOW() - $2::interval
        """,
        domain,
        timedelta(days=DOMAIN_CACHE_DAYS),
    )
    if not row:
        return None

    emails = await get_supplier_emails(conn, row["id"])
    if not emails:
        return None  # домен есть, но email не нашли — лучше перепарсить

    return {"supplier_id": row["id"], "emails": emails}


async def touch_supplier(conn: asyncpg.Connection, supplier_id: int):
    """Обновляет updated_at чтобы продлить кэш."""
    await conn.execute(
        "UPDATE suppliers SET updated_at = NOW() WHERE id = $1", supplier_id
    )


# ---------------------------------------------------------------------------
# Дополнительные функции для просмотра и отладки
# ---------------------------------------------------------------------------

async def get_all_suppliers_with_emails(conn: asyncpg.Connection) -> list[dict]:
    """Возвращает всех поставщиков с их email."""
    rows = await conn.fetch("""
        SELECT 
            s.id,
            s.domain,
            s.source_url,
            s.created_at,
            array_agg(se.email) as emails
        FROM suppliers s
        LEFT JOIN supplier_emails se ON s.id = se.supplier_id
        GROUP BY s.id
        ORDER BY s.id
    """)
    
    return [
        {
            "id": r["id"],
            "domain": r["domain"],
            "source_url": r["source_url"],
            "created_at": r["created_at"],
            "emails": r["emails"] if r["emails"] else []
        }
        for r in rows
    ]


async def search_email(conn: asyncpg.Connection, email_pattern: str) -> list[dict]:
    """Поиск email по паттерну (поддерживает LIKE)."""
    rows = await conn.fetch("""
        SELECT 
            s.domain,
            se.email,
            se.page_type,
            se.source_url,
            se.created_at
        FROM supplier_emails se
        JOIN suppliers s ON s.id = se.supplier_id
        WHERE se.email LIKE $1
        ORDER BY se.email
    """, f"%{email_pattern}%")
    
    return [
        {
            "domain": r["domain"],
            "email": r["email"],
            "page_type": r["page_type"],
            "source_url": r["source_url"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]


async def get_stats(conn: asyncpg.Connection) -> dict:
    """Возвращает статистику по базе данных."""
    stats = await conn.fetchrow("""
        SELECT 
            COUNT(DISTINCT s.id) as suppliers_count,
            COUNT(se.id) as emails_count,
            COUNT(DISTINCT ssr.item_id) as items_searched
        FROM suppliers s
        LEFT JOIN supplier_emails se ON s.id = se.supplier_id
        LEFT JOIN supplier_search_results ssr ON s.id = ssr.supplier_id
    """)
    
    return {
        "suppliers_count": stats["suppliers_count"],
        "emails_count": stats["emails_count"],
        "items_searched": stats["items_searched"]
    }