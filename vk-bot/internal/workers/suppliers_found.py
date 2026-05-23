"""Suppliers found worker — notifies VK user when suppliers are found for items."""

import logging
from vkbottle import Bot

from ..repository.postgres import PostgresRepository
from ..repository.redis import RedisRepositoryImpl

logger = logging.getLogger(__name__)


class SuppliersFoundWorker:
    def __init__(
        self, pg: PostgresRepository, redis_repo: RedisRepositoryImpl, bot: Bot
    ):
        self.pg = pg
        self.redis = redis_repo
        self.bot = bot

    async def run(self):
        await self.redis.subscribe_suppliers_found(self._on_suppliers_found)
        logger.info("Suppliers found worker started")

    async def _on_suppliers_found(self, data: dict):
        try:
            item_id = int(data.get("item_id", 0))
            item_name = data.get("item_name", "")
            emails_count = int(data.get("emails_count", 0))

            item = await self.pg.get_item_by_id(item_id)
            if not item:
                logger.warning(f"Item {item_id} not found for suppliers notification")
                return

            rfq_id = item["rfq_id"]
            rfq = await self.pg.get_rfq_by_id(rfq_id)
            if not rfq:
                logger.warning(f"RFQ {rfq_id} not found for suppliers notification")
                return

            creator_vk_id = rfq.get("created_by_vk")
            if not creator_vk_id:
                logger.warning(f"RFQ {rfq_id} has no creator_vk_id")
                return

            await self.bot.api.messages.send(
                peer_id=creator_vk_id,
                message=(
                    f"🔍 Найдены поставщики для позиции:\n"
                    f"• {item_name[:60]}\n"
                    f"• {emails_count} email(-ов) найдено\n"
                    f"Рассылаю коммерческие предложения..."
                ),
                random_id=0,
            )

            logger.info(
                f"Suppliers found notification sent for RFQ {rfq_id}, "
                f"item {item_id}, {emails_count} emails"
            )

        except Exception as e:
            logger.exception(f"Error processing suppliers_found: {e}")
