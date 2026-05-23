"""Quote tracker worker — sends real-time status updates to VK user."""

import logging
from vkbottle import Bot

from ..repository.postgres import PostgresRepository
from ..repository.redis import RedisRepositoryImpl

logger = logging.getLogger(__name__)


class QuoteTrackerWorker:
    def __init__(
        self, pg: PostgresRepository, redis_repo: RedisRepositoryImpl, bot: Bot
    ):
        self.pg = pg
        self.redis = redis_repo
        self.bot = bot

    async def run(self):
        await self.redis.subscribe_quote_received(self._on_quote_received)
        logger.info("Quote tracker worker started")

    async def _on_quote_received(self, data: dict):
        try:
            item_id = int(data.get("item_id", 0))
            supplier_id = int(data.get("supplier_id", 0))
            price = data.get("price", "0")
            delivery_days = data.get("delivery_days", "0")
            supplier_email = data.get("supplier_email", "")

            item = await self.pg.get_item_by_id(item_id)
            if not item:
                logger.warning(f"Item {item_id} not found for quote notification")
                return

            rfq_id = item["rfq_id"]
            rfq = await self.pg.get_rfq_by_id(rfq_id)
            if not rfq:
                return

            creator_vk_id = rfq.get("created_by_vk")
            if not creator_vk_id:
                return

            status = await self.pg.get_rfq_status(rfq_id)
            total = status["total"]
            quoted = status["quoted"]

            domain = supplier_email.split("@")[-1] if "@" in supplier_email else supplier_email

            pct = int(quoted / total * 100) if total > 0 else 0

            await self.bot.api.messages.send(
                peer_id=creator_vk_id,
                message=(
                    f"📩 Получена котировка от {domain}\n"
                    f"• Позиция: {item['name'][:50]}\n"
                    f"• Цена: {price} р.\n"
                    f"• Срок: {delivery_days} дн.\n"
                    f"• Собрано: {quoted}/{total} ({pct}%)"
                ),
                random_id=0,
            )

            logger.info(
                f"Quote notification sent for item {item_id}, "
                f"progress {quoted}/{total}"
            )

        except Exception as e:
            logger.exception(f"Error processing quote: {e}")
