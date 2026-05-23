"""Aggregator service for winner selection."""

from datetime import datetime, date, timezone
from typing import List, Optional

import asyncpg

from ..domain.models import Quote, Winner, Item


class Aggregator:
    """Aggregator for winner selection."""

    def __init__(self, margin_percent: float, pg: asyncpg.Pool):
        self.margin_percent = margin_percent
        self.pg = pg

    async def select_winner(
        self, item_id: int, quotes: List[Quote], item: Item
    ) -> Optional[Winner]:
        """Select winner for an item with advisory lock to prevent race conditions."""
        if not quotes:
            return None

        # Acquire advisory lock for this item to prevent concurrent updates
        async with self.pg.acquire() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock($1)", item_id)

            # Re-fetch quotes within transaction to ensure consistency
            rows = await conn.fetch(
                """
                SELECT id, item_id, supplier_id, supplier_email, price,
                       delivery_days, pickup_address, source, received_at
                FROM quotes WHERE item_id = $1 ORDER BY received_at
                """,
                item_id,
            )
            current_quotes = [
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

            # Convert date to timezone-aware datetime
            now = datetime.now(timezone.utc)
            if isinstance(item.deadline, date) and not isinstance(item.deadline, datetime):
                deadline = datetime.combine(item.deadline, datetime.min.time(), tzinfo=timezone.utc)
            else:
                deadline = item.deadline
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)

            days_until_deadline = (deadline - now).days

            valid_quotes = [
                q for q in current_quotes if q.delivery_days <= days_until_deadline
            ]

            if not valid_quotes:
                valid_quotes = current_quotes
                valid_quotes.sort(key=lambda q: q.delivery_days)
            else:
                valid_quotes.sort(key=lambda q: (q.price, q.delivery_days))

            if not valid_quotes:
                return None

            best_quote = valid_quotes[0]
            final_price = best_quote.price * (1 + self.margin_percent / 100)

            return Winner(
                id=0,
                item_id=item_id,
                quote_id=best_quote.id,
                final_price=round(final_price, 2),
                margin_pct=self.margin_percent,
                chosen_at=datetime.now(timezone.utc),
            )