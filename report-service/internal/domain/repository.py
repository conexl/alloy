"""Repository interfaces."""

from typing import Protocol, Optional, List
from .models import Quote, Winner, Item, Supplier, RFQStatus


class PostgreSQLRepository(Protocol):
    """PostgreSQL repository protocol."""

    async def get_item(self, item_id: int) -> Optional[Item]:
        """Get item by ID."""
        ...

    async def get_items_by_rfq(self, rfq_id: int) -> List[Item]:
        """Get all items for RFQ."""
        ...

    async def get_quotes_for_item(self, item_id: int) -> List[Quote]:
        """Get all quotes for an item."""
        ...

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
        ...

    async def upsert_winner(
        self, item_id: int, quote_id: int, final_price: float, margin_pct: float
    ) -> Winner:
        """Insert or update winner if final_price is better."""
        ...

    async def get_winner(self, item_id: int) -> Optional[Winner]:
        """Get current winner for item."""
        ...

    async def get_rfq_status(self, rfq_id: int) -> RFQStatus:
        """Get processing status for RFQ."""
        ...

    async def is_rfq_complete(self, rfq_id: int) -> bool:
        """Check if all items have winners."""
        ...

    async def get_full_report_data(self, rfq_id: int) -> List[dict]:
        """Get complete report data with joins."""
        ...

    async def get_supplier(self, supplier_id: int) -> Optional[Supplier]:
        """Get supplier by ID."""
        ...

    async def get_overdue_rfqs(self) -> List[int]:
        """Get list of RFQ IDs where deadline passed but not all items complete."""
        ...

    async def get_user_profile(self, rfq_id: int) -> Optional[dict]:
        """Get user profile for the RFQ creator."""
        ...


class RedisRepository(Protocol):
    """Redis repository protocol."""

    async def read_quote_received(self) -> list:
        """Read messages from quote_received stream."""
        ...

    async def ack_quote(self, stream: str, group: str, message_id: str) -> None:
        """Acknowledge message processing."""
        ...

    async def publish_report_ready(self, rfq_id: int, file_key: str) -> None:
        """Publish report_ready event."""
        ...

    async def create_consumer_group(self, stream: str, group: str) -> None:
        """Create consumer group if not exists."""
        ...

    async def ping(self) -> bool:
        """Ping Redis."""
        ...
