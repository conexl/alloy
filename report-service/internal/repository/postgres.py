"""PostgreSQL repository implementation."""

import asyncpg
from typing import Optional, List
from datetime import datetime

from ..domain.models import Quote, Winner, Item, Supplier, RFQStatus
from ..domain.repository import PostgreSQLRepository


class PostgresRepository(PostgreSQLRepository):
    """PostgreSQL repository implementation."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create connection pool."""
        self._pool = await asyncpg.create_pool(self.dsn)

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()

    async def get_item(self, item_id: int) -> Optional[Item]:
        """Get item by ID."""
        query = """
            SELECT id, rfq_id, name, tech_code, material, gost,
                   tt_ol_ref, unit, qty, deadline, location, rkd_ref, payment_terms
            FROM items WHERE id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, item_id)
            if not row:
                return None
            return Item(
                id=row["id"],
                rfq_id=row["rfq_id"],
                name=row["name"],
                tech_code=row["tech_code"],
                material=row["material"],
                gost=row["gost"],
                tt_ol_ref=row["tt_ol_ref"],
                unit=row["unit"],
                qty=float(row["qty"]),
                deadline=row["deadline"],
                location=row["location"],
                rkd_ref=row["rkd_ref"],
                payment_terms=row["payment_terms"],
            )

    async def get_items_by_rfq(self, rfq_id: int) -> List[Item]:
        """Get all items for RFQ."""
        query = """
            SELECT id, rfq_id, name, tech_code, material, gost,
                   tt_ol_ref, unit, qty, deadline, location, rkd_ref, payment_terms
            FROM items WHERE rfq_id = $1 ORDER BY id
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, rfq_id)
            return [
Item(
                        id=r["id"],
                        rfq_id=r["rfq_id"],
                        name=r["name"],
                        tech_code=r["tech_code"],
                        material=r["material"],
                        gost=r["gost"],
                        tt_ol_ref=r["tt_ol_ref"],
                        unit=r["unit"],
                        qty=float(r["qty"]),
                        deadline=r["deadline"],
                        location=r["location"],
                        rkd_ref=r["rkd_ref"],
                        payment_terms=r["payment_terms"],
                    )
                for r in rows
            ]

    async def get_quotes_for_item(self, item_id: int) -> List[Quote]:
        """Get all quotes for an item."""
        query = """
            SELECT id, item_id, supplier_id, supplier_email, price,
                   delivery_days, pickup_address, source, received_at
            FROM quotes WHERE item_id = $1 ORDER BY received_at
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, item_id)
            return [
                Quote(
                    id=r["id"],
                    item_id=r["item_id"],
                    supplier_id=r["supplier_id"],
                    supplier_email=r["supplier_email"],
                    price=float(r["price"]),
                    delivery_days=r["delivery_days"] or 0,
                    pickup_address=r["pickup_address"],
                    source=r["source"],
                    received_at=r["received_at"],
                )
                for r in rows
            ]

    async def upsert_quote(
        self,
        item_id: int,
        supplier_id: int,
        supplier_email: str,
        price: float,
        delivery_days: int,
        pickup_address: Optional[str],
        source: str,
    ) -> Quote:
        """Insert or update quote if price is better."""
        query = """
            INSERT INTO quotes (item_id, supplier_id, supplier_email, price,
                                delivery_days, pickup_address, source, received_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            ON CONFLICT (item_id, supplier_id)
            DO UPDATE SET
                price = EXCLUDED.price,
                delivery_days = EXCLUDED.delivery_days,
                pickup_address = EXCLUDED.pickup_address,
                received_at = NOW()
            WHERE EXCLUDED.price < quotes.price
            RETURNING id
        """
        async with self._pool.acquire() as conn:
            quote_id = await conn.fetchval(
                query,
                item_id,
                supplier_id,
                supplier_email,
                price,
                delivery_days,
                pickup_address,
                source,
            )
            if not quote_id:
                # Conflict but price not better, fetch existing
                row = await conn.fetchrow(
                    "SELECT id FROM quotes WHERE item_id=$1 AND supplier_id=$2",
                    item_id,
                    supplier_id,
                )
                quote_id = row["id"]
            quote = await self._get_quote_by_id(quote_id)
            return quote

    async def _get_quote_by_id(self, quote_id: int) -> Quote:
        """Helper to get quote by ID."""
        query = """
            SELECT id, item_id, supplier_id, supplier_email, price,
                   delivery_days, pickup_address, source, received_at
            FROM quotes WHERE id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, quote_id)
            return Quote(
                id=row["id"],
                item_id=row["item_id"],
                supplier_id=row["supplier_id"],
                supplier_email=row["supplier_email"],
                price=float(row["price"]),
                delivery_days=row["delivery_days"] or 0,
                pickup_address=row["pickup_address"],
                source=row["source"],
                received_at=row["received_at"],
            )

    async def upsert_winner(
        self, item_id: int, quote_id: int, final_price: float, margin_pct: float
    ) -> Winner:
        """Insert or update winner if final_price is better."""
        query = """
            INSERT INTO winners (item_id, quote_id, final_price, margin_pct, chosen_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (item_id)
            DO UPDATE SET
                quote_id = EXCLUDED.quote_id,
                final_price = EXCLUDED.final_price,
                chosen_at = NOW()
            WHERE EXCLUDED.final_price < winners.final_price
            RETURNING id
        """
        async with self._pool.acquire() as conn:
            winner_id = await conn.fetchval(
                query, item_id, quote_id, final_price, margin_pct
            )
            if not winner_id:
                # Conflict but price not better, fetch existing
                row = await conn.fetchrow(
                    "SELECT id FROM winners WHERE item_id = $1", item_id
                )
                winner_id = row["id"]
            winner = await self._get_winner_by_id(winner_id)
            return winner

    async def _get_winner_by_id(self, winner_id: int) -> Winner:
        """Helper to get winner by ID."""
        query = """
            SELECT id, item_id, quote_id, final_price, margin_pct, chosen_at
            FROM winners WHERE id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, winner_id)
            return Winner(
                id=row["id"],
                item_id=row["item_id"],
                quote_id=row["quote_id"],
                final_price=float(row["final_price"]),
                margin_pct=float(row["margin_pct"]),
                chosen_at=row["chosen_at"],
            )

    async def get_winner(self, item_id: int) -> Optional[Winner]:
        """Get current winner for item."""
        query = """
            SELECT id, item_id, quote_id, final_price, margin_pct, chosen_at
            FROM winners WHERE item_id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, item_id)
            if not row:
                return None
            return Winner(
                id=row["id"],
                item_id=row["item_id"],
                quote_id=row["quote_id"],
                final_price=float(row["final_price"]),
                margin_pct=float(row["margin_pct"]),
                chosen_at=row["chosen_at"],
            )

    async def get_rfq_status(self, rfq_id: int) -> RFQStatus:
        """Get processing status for RFQ."""
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
            return RFQStatus(
                rfq_id=rfq_id,
                total=row["total"],
                quoted=row["quoted"],
                winners=row["winners"],
                ready=row["winners"] == row["total"],
            )

    async def is_rfq_complete(self, rfq_id: int) -> bool:
        """Check if all items have winners."""
        query = """
            SELECT COUNT(*) = COUNT(w.id) AS complete
            FROM items i
            LEFT JOIN winners w ON w.item_id = i.id
            WHERE i.rfq_id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, rfq_id)
            return row["complete"]

    async def get_full_report_data(self, rfq_id: int) -> List[dict]:
        """Get complete report data with joins."""
        query = """
            SELECT
                ROW_NUMBER() OVER (ORDER BY i.id) AS num,
                i.name, i.tech_code, i.material, i.gost,
                i.tt_ol_ref, i.unit, i.qty, i.deadline,
                i.location, i.rkd_ref, i.payment_terms,
                w.final_price,
                q.supplier_email,
                q.delivery_days,
                q.pickup_address,
                s.name AS supplier_name
            FROM items i
            LEFT JOIN winners w ON w.item_id = i.id
            LEFT JOIN quotes q ON q.id = w.quote_id
            LEFT JOIN suppliers s ON s.id = q.supplier_id
            LEFT JOIN supplier_emails se ON se.supplier_id = s.id AND se.email = q.supplier_email
            WHERE i.rfq_id = $1
            ORDER BY i.id
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, rfq_id)
            return [dict(row) for row in rows]

    async def get_supplier(self, supplier_id: int) -> Optional[Supplier]:
        """Get supplier by ID."""
        query = "SELECT id, name FROM suppliers WHERE id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, supplier_id)
            if not row:
                return None
            return Supplier(id=row["id"], name=row["name"])

    async def get_overdue_rfqs(self) -> List[int]:
        """Get list of RFQ IDs where deadline passed but not all items have winners."""
        query = """
            SELECT DISTINCT i.rfq_id
            FROM items i
            LEFT JOIN winners w ON w.item_id = i.id
            WHERE i.deadline < NOW()
              AND w.id IS NULL
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [r["rfq_id"] for r in rows]

    async def get_user_profile(self, rfq_id: int) -> Optional[dict]:
        query = """
            SELECT
                up.company_name, up.inn, up.kpp, up.address,
                up.phone, up.email, up.contact_person
            FROM rfq_requests r
            JOIN user_profiles up ON up.vk_id = r.created_by_vk
            WHERE r.id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, rfq_id)
            return dict(row) if row else None
