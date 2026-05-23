"""Redis repository."""

import asyncio
import redis.asyncio as redis
from typing import List

from ..domain.repository import RedisRepository


class RedisRepositoryImpl(RedisRepository):
    def __init__(self, url: str):
        self.url = url
        self._client = None

    async def connect(self):
        self._client = redis.from_url(self.url)

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def publish_new_rfq(self, rfq_id: int, items: List[dict]):
        import json
        from datetime import datetime

        def convert_dates(item):
            d = dict(item)
            if isinstance(d.get("deadline"), datetime):
                d["deadline"] = d["deadline"].strftime("%Y-%m-%d")
            return d

        clean_items = [convert_dates(it) for it in items]

        await self._client.xadd(
            "new_rfq", {"rfq_id": str(rfq_id), "items": json.dumps(clean_items)}
        )

    async def subscribe_report_ready(self, callback):
        try:
            await self._client.xgroup_create(
                "report_ready", "vk-bot-group", id="0", mkstream=True
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        asyncio.create_task(self._listen_report_ready(callback))

    async def subscribe_quote_received(self, callback):
        try:
            await self._client.xgroup_create(
                "quote_received", "vk-bot-quote-group", id="0", mkstream=True
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        asyncio.create_task(self._listen_quote_received(callback))

    async def _listen_report_ready(self, callback):
        import json

        while True:
            try:
                msgs = await self._client.xreadgroup(
                    "vk-bot-group", "vk-bot", {"report_ready": ">"}, count=1, block=5000
                )
                if msgs:
                    for stream_name, events in msgs:
                        for msg_id, data in events:
                            decoded = {k.decode(): v.decode() for k, v in data.items()}
                            await callback(decoded)
                            await self._client.xack("report_ready", "vk-bot-group", msg_id)
            except Exception:
                await asyncio.sleep(1)

    async def subscribe_suppliers_found(self, callback):
        try:
            await self._client.xgroup_create(
                "suppliers_found", "vk-bot-suppliers-group", id="0", mkstream=True
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        asyncio.create_task(self._listen_suppliers_found(callback))

    async def _listen_suppliers_found(self, callback):
        while True:
            try:
                msgs = await self._client.xreadgroup(
                    "vk-bot-suppliers-group", "vk-bot-suppliers",
                    {"suppliers_found": ">"}, count=1, block=5000
                )
                if msgs:
                    for stream_name, events in msgs:
                        for msg_id, data in events:
                            decoded = {k.decode(): v.decode() for k, v in data.items()}
                            await callback(decoded)
                            await self._client.xack("suppliers_found", "vk-bot-suppliers-group", msg_id)
            except Exception:
                await asyncio.sleep(1)

    async def _listen_quote_received(self, callback):
        import json

        while True:
            try:
                msgs = await self._client.xreadgroup(
                    "vk-bot-quote-group", "vk-bot-quote", {"quote_received": ">"}, count=1, block=5000
                )
                if msgs:
                    for stream_name, events in msgs:
                        for msg_id, data in events:
                            decoded = {k.decode(): v.decode() for k, v in data.items()}
                            await callback(decoded)
                            await self._client.xack("quote_received", "vk-bot-quote-group", msg_id)
            except Exception:
                await asyncio.sleep(1)

    async def publish_user_quote(
        self,
        user_id: int,
        item_id: int,
        supplier_id: int,
        price: float,
        delivery_days: int,
    ):
        await self._client.xadd(
            "quote_received",
            {
                "item_id": str(item_id),
                "supplier_id": str(supplier_id),
                "supplier_email": f"vk_user_{user_id}@vk.bot",
                "price": str(price),
                "delivery_days": str(delivery_days),
                "pickup_address": "",
                "source": "vk",
            },
        )
