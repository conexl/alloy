"""Redis repository implementation."""

import redis.asyncio as redis
from redis.asyncio import Redis
from typing import List, Optional

from ..domain.repository import RedisRepository


class RedisRepositoryImpl(RedisRepository):
    """Redis repository implementation."""

    def __init__(self, url: str):
        self.url = url
        self._client: Optional[Redis] = None

    async def connect(self):
        """Connect to Redis."""
        self._client = redis.from_url(self.url, decode_responses=True)

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()

    async def ping(self) -> bool:
        """Ping Redis."""
        try:
            return await self._client.ping()
        except Exception:
            return False

    async def create_consumer_group(self, stream: str, group: str):
        """Create consumer group if not exists."""
        try:
            await self._client.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def read_quote_received(self) -> List[dict]:
        """Read messages from quote_received stream."""
        messages = []
        try:
            msgs = await self._client.xreadgroup(
                groupname="report-group",
                consumername="report-worker",
                streams={"quote_received": ">"},
                count=10,
                block=5000,
            )
            for stream_name, stream_messages in msgs:
                for message_id, message in stream_messages:
                    messages.append({"id": message_id, "data": message})
        except Exception:
            pass
        return messages

    async def ack_quote(self, stream: str, group: str, message_id: str):
        """Acknowledge message processing."""
        await self._client.xack(stream, group, message_id)

    async def publish_report_ready(self, rfq_id: int, file_key: str):
        """Publish report_ready event."""
        await self._client.xadd(
            "report_ready", {"rfq_id": str(rfq_id), "file_key": file_key}
        )
