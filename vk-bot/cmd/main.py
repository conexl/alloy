"""Main entry point — single catch-all handler for all routing."""

import asyncio
import logging

from vkbottle import Bot

from internal.config.config import get_settings
from internal.repository.postgres import PostgresRepository
from internal.repository.redis import RedisRepositoryImpl
from internal.handlers.bot_handlers import BotHandlers
from internal.workers.report_ready import ReportReadyWorker
from internal.workers.quote_tracker import QuoteTrackerWorker
from internal.workers.suppliers_found import SuppliersFoundWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
bot = Bot(token=settings.vk_group_token)
pg = PostgresRepository(settings.db_dsn)
redis_repo = RedisRepositoryImpl(settings.redis_url)
handlers = BotHandlers(pg, redis_repo, settings.report_service_url)


@bot.on.message()
async def message_handler(message):
    await handlers.route(message)


async def polling_loop():
    _polling = bot.polling
    logger.info("VK bot polling started...")
    async for event in _polling.listen():
        for update in event.get("updates", []):
            loop = asyncio.get_running_loop()
            loop.create_task(bot.router.route(update, _polling.api))


async def main():
    await pg.connect()
    await redis_repo.connect()
    report_worker = ReportReadyWorker(pg, redis_repo, bot)
    asyncio.create_task(report_worker.run())
    quote_tracker = QuoteTrackerWorker(pg, redis_repo, bot)
    asyncio.create_task(quote_tracker.run())
    suppliers_worker = SuppliersFoundWorker(pg, redis_repo, bot)
    asyncio.create_task(suppliers_worker.run())
    await polling_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")