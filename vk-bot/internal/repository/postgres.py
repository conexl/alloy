"""PostgreSQL repository."""

import asyncpg
from typing import Optional, List
from datetime import datetime

from ..domain.models import User, RFQ, UserProfile
from ..domain.repository import PostgreSQLRepository


class PostgresRepository(PostgreSQLRepository):
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool = None

    async def connect(self):
        self._pool = await asyncpg.create_pool(self.dsn)

    async def close(self):
        if self._pool:
            await self._pool.close()

    async def get_user(self, vk_id: int) -> Optional[User]:
        query = "SELECT vk_id, vk_name, is_active, created_at FROM vk_users WHERE vk_id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, vk_id)
            if not row:
                return None
            return User(**row)

    async def create_user(self, vk_id: int, vk_name: str) -> User:
        query = """
            INSERT INTO vk_users (vk_id, vk_name, is_active, created_at)
            VALUES ($1, $2, true, NOW())
            ON CONFLICT (vk_id) DO UPDATE SET vk_name = $2
            RETURNING vk_id, vk_name, is_active, created_at
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, vk_id, vk_name)
            return User(**row)

    async def get_active_users(self) -> List[User]:
        query = "SELECT vk_id, vk_name, is_active, created_at FROM vk_users WHERE is_active = true"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [User(**r) for r in rows]

    async def create_rfq(
        self,
        items: List[dict],
        city: str,
        total_budget: Optional[float] = None,
        created_by_vk: int = None,
    ) -> int:
        query = """
            INSERT INTO rfq_requests (city, total_budget, created_by_vk, created_at)
            VALUES ($1, $2, $3, NOW())
            RETURNING id
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rfq_id = await conn.fetchval(query, city, total_budget, created_by_vk)
                for item in items:
                    item_id = await conn.fetchval(
                        """
                        INSERT INTO items 
                            (rfq_id, name, tech_code, gost, unit, qty,
                             deadline, location, payment_terms, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                        RETURNING id
                    """,
                        rfq_id,
                        item["name"],
                        item.get("tech_code"),
                        item.get("gost"),
                        item.get("unit", "шт"),
                        int(item["qty"]),
                        item["deadline"],
                        item.get("location", city),
                        item.get("payment_terms"),
                    )
                    item["id"] = item_id
                return rfq_id

    async def get_latest_rfq_for_user(self, vk_id: int) -> Optional[RFQ]:
        query = """
            SELECT r.id as rfq_id, r.city, r.total_budget,
                   COUNT(i.id) as items_count
            FROM rfq_requests r
            JOIN items i ON i.rfq_id = r.id
            WHERE r.created_by_vk = $1
            GROUP BY r.id
            ORDER BY r.created_at DESC
            LIMIT 1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, vk_id)
            if not row:
                return None
            return RFQ(
                rfq_id=row["rfq_id"],
                item_id=0,
                item_name=f"Заявка {row['rfq_id']}",
                tech_code=None,
                material=None,
                gost=None,
                unit="",
                qty=0,
                deadline=datetime.now(),
                location=row["city"],
                payment_terms=None,
                suppliers=[],
            )

    async def get_rfq_status(self, rfq_id: int) -> dict:
        query = """
            SELECT
                COUNT(*) AS total,
                COUNT(q.id) AS quoted,
                COUNT(w.id) AS winners
            FROM items i
            LEFT JOIN quotes q ON q.item_id = i.id
            LEFT JOIN winners w ON w.item_id = i.id
            WHERE i.rfq_id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, rfq_id)
            return {
                "rfq_id": rfq_id,
                "total": row["total"],
                "quoted": row["quoted"],
                "winners": row["winners"],
                "ready": row["winners"] == row["total"],
            }

    async def get_rfq_items_status(self, rfq_id: int) -> list[dict]:
        query = """
            SELECT
                i.id, i.name, i.qty, i.unit, i.deadline, i.location,
                COUNT(DISTINCT q.id)::int AS quote_count,
                COUNT(DISTINCT w.id)::int AS winner_count,
                COUNT(DISTINCT ssr.supplier_id)::int AS supplier_count,
                MIN(q.price) AS min_price
            FROM items i
            LEFT JOIN quotes q ON q.item_id = i.id
            LEFT JOIN winners w ON w.item_id = i.id
            LEFT JOIN supplier_search_results ssr ON ssr.item_id = i.id
            WHERE i.rfq_id = $1
            GROUP BY i.id
            ORDER BY i.id
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, rfq_id)
            return [dict(r) for r in rows]

    async def get_user_rfqs(self, vk_id: int) -> list[dict]:
        query = """
            SELECT r.id, r.city, r.total_budget, r.created_at,
                   COUNT(DISTINCT i.id)::int AS items_count,
                   COUNT(DISTINCT q.id)::int AS quoted_count,
                   COUNT(DISTINCT w.id)::int AS winner_count,
                   COUNT(DISTINCT ssr.supplier_id)::int AS supplier_count
            FROM rfq_requests r
            JOIN items i ON i.rfq_id = r.id
            LEFT JOIN quotes q ON q.item_id = i.id
            LEFT JOIN winners w ON w.item_id = i.id
            LEFT JOIN supplier_search_results ssr ON ssr.item_id = i.id
            WHERE r.created_by_vk = $1
            GROUP BY r.id
            ORDER BY r.created_at DESC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, vk_id)
            return [dict(r) for r in rows]

    async def get_rfq_quotes_for_item(self, item_id: int) -> list[dict]:
        query = """
            SELECT q.id, q.price, q.delivery_days, s.name AS supplier_name,
                   w.id IS NOT NULL AS is_winner
            FROM quotes q
            JOIN suppliers s ON s.id = q.supplier_id
            LEFT JOIN winners w ON w.item_id = q.item_id AND w.quote_id = q.id
            WHERE q.item_id = $1
            ORDER BY q.price ASC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, item_id)
            return [dict(r) for r in rows]

    async def get_rfq_supplier_summary(self, rfq_id: int) -> list[dict]:
        query = """
            SELECT DISTINCT s.id, s.name, s.domain
            FROM suppliers s
            JOIN supplier_search_results ssr ON ssr.supplier_id = s.id
            JOIN items i ON i.id = ssr.item_id
            WHERE i.rfq_id = $1
            ORDER BY s.name
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, rfq_id)
            return [dict(r) for r in rows]

    async def get_rfq_items_status(self, rfq_id: int) -> list[dict]:
        query = """
            SELECT
                i.id, i.name, i.qty, i.unit, i.deadline, i.location,
                COUNT(DISTINCT q.id)::int AS quote_count,
                COUNT(DISTINCT w.id)::int AS winner_count,
                COUNT(DISTINCT ssr.supplier_id)::int AS supplier_count,
                MIN(q.price) AS min_price
            FROM items i
            LEFT JOIN quotes q ON q.item_id = i.id
            LEFT JOIN winners w ON w.item_id = i.id
            LEFT JOIN supplier_search_results ssr ON ssr.item_id = i.id
            WHERE i.rfq_id = $1
            GROUP BY i.id
            ORDER BY i.id
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, rfq_id)
            return [dict(r) for r in rows]

    async def get_user_rfqs(self, vk_id: int) -> list[dict]:
        query = """
            SELECT r.id, r.city, r.total_budget, r.created_at,
                   COUNT(DISTINCT i.id)::int AS items_count,
                   COUNT(DISTINCT q.id)::int AS quoted_count,
                   COUNT(DISTINCT w.id)::int AS winner_count,
                   COUNT(DISTINCT ssr.supplier_id)::int AS supplier_count
            FROM rfq_requests r
            JOIN items i ON i.rfq_id = r.id
            LEFT JOIN quotes q ON q.item_id = i.id
            LEFT JOIN winners w ON w.item_id = i.id
            LEFT JOIN supplier_search_results ssr ON ssr.item_id = i.id
            WHERE r.created_by_vk = $1
            GROUP BY r.id
            ORDER BY r.created_at DESC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, vk_id)
            return [dict(r) for r in rows]

    async def get_rfq_quotes_for_item(self, item_id: int) -> list[dict]:
        query = """
            SELECT q.id, q.price, q.delivery_days, s.name AS supplier_name,
                   w.id IS NOT NULL AS is_winner
            FROM quotes q
            JOIN suppliers s ON s.id = q.supplier_id
            LEFT JOIN winners w ON w.item_id = q.item_id AND w.quote_id = q.id
            WHERE q.item_id = $1
            ORDER BY q.price ASC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, item_id)
            return [dict(r) for r in rows]

    async def get_rfq_supplier_summary(self, rfq_id: int) -> list[dict]:
        query = """
            SELECT DISTINCT s.id, s.name, s.domain
            FROM suppliers s
            JOIN supplier_search_results ssr ON ssr.supplier_id = s.id
            JOIN items i ON i.id = ssr.item_id
            WHERE i.rfq_id = $1
            ORDER BY s.name
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, rfq_id)
            return [dict(r) for r in rows]

    async def get_suppliers_by_item(self, item_id: int) -> List[dict]:
        query = """
            SELECT DISTINCT s.id, s.name, q.supplier_email
            FROM quotes q
            JOIN suppliers s ON s.id = q.supplier_id
            WHERE q.item_id = $1
            ORDER BY s.name
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, item_id)
            return [
                {
                    "supplier_id": r["id"],
                    "name": r["name"],
                    "emails": [r["supplier_email"]] if r["supplier_email"] else [],
                }
                for r in rows
            ]

    async def get_rfq_by_id(self, rfq_id: int) -> Optional[dict]:
        """Get RFQ with items."""
        query = """
            SELECT r.id, r.city, r.total_budget, r.created_by_vk,
                   COUNT(i.id) as items_count
            FROM rfq_requests r
            JOIN items i ON i.rfq_id = r.id
            WHERE r.id = $1
            GROUP BY r.id
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, rfq_id)
            return dict(row) if row else None

    async def get_item_by_id(self, item_id: int) -> Optional[dict]:
        query = """
            SELECT i.id, i.name, i.rfq_id, i.qty, i.unit, i.tech_code
            FROM items i
            WHERE i.id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, item_id)
            return dict(row) if row else None

    async def get_profile(self, vk_id: int) -> Optional[UserProfile]:
        query = """
            SELECT vk_id, company_name, inn, kpp, address, phone, email, contact_person
            FROM user_profiles WHERE vk_id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, vk_id)
            return UserProfile(**row) if row else None

    async def upsert_profile(self, profile: UserProfile) -> UserProfile:
        query = """
            INSERT INTO user_profiles (vk_id, company_name, inn, kpp, address, phone, email, contact_person)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (vk_id) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                inn = EXCLUDED.inn,
                kpp = EXCLUDED.kpp,
                address = EXCLUDED.address,
                phone = EXCLUDED.phone,
                email = EXCLUDED.email,
                contact_person = EXCLUDED.contact_person,
                updated_at = NOW()
            RETURNING vk_id, company_name, inn, kpp, address, phone, email, contact_person
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query, profile.vk_id, profile.company_name,
                profile.inn, profile.kpp, profile.address,
                profile.phone, profile.email, profile.contact_person,
            )
            return UserProfile(**row)
