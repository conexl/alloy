"""App factory."""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .config.config import get_settings
from .repository.postgres import PostgresRepository
from .repository.redis import RedisRepositoryImpl
from .handlers.bot_handlers import BotHandlers
from .workers.report_ready import ReportReadyWorker

from vkbottle import Bot

_pg_repo = None
_redis_repo = None
_bot = None
_report_worker = None
_handlers = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pg_repo, _redis_repo, _bot, _report_worker, _handlers

    settings = get_settings()

    _pg_repo = PostgresRepository(settings.db_dsn)
    await _pg_repo.connect()

    _redis_repo = RedisRepositoryImpl(settings.redis_url)
    await _redis_repo.connect()

    _bot = Bot(token=settings.vk_group_token)
    _handlers = BotHandlers(_pg_repo, _redis_repo, settings.report_service_url)
    _bot.labeler.vbml_ignore_case = True

    @_bot.on.message(text=["начать", "старт", "start", "привет", "помощь", "❓ помощь"])
    async def start_wrapper(message):
        await _handlers.start_handler(message)

    @_bot.on.message(text=["статус", "status", "📊 статус последней", "📊 статус"])
    async def status_wrapper(message):
        await _handlers.status_handler(message)

    @_bot.on.message(text=["отчёт", "отчет", "report", "📄 получить отчёт", "📄 отчёт"])
    async def report_wrapper(message):
        await _handlers.report_handler(message)

    @_bot.on.message(text=["новая заявка", "заявка", "➕ новая заявка"])
    async def new_rfq_wrapper(message):
        await _handlers.new_rfq_handler(message)

    @_bot.on.message(attachment="doc")
    async def file_wrapper(message):
        await _handlers.file_handler(message)

    @_bot.on.message(text=["✅ подтвердить", "да", "подтвердить"])
    async def confirm_wrapper(message):
        await _handlers.confirm_handler(message)

    @_bot.on.message(text=["❌ отмена", "отмена", "назад"])
    async def cancel_wrapper(message):
        await _handlers.cancel_handler(message)

    @_bot.on.message(text=["мои заявки", "заявки", "список заявок", "📋 мои заявки"])
    async def my_rfqs_wrapper(message):
        await _handlers.my_rfqs_handler(message)

    @_bot.on.message()
    async def text_wrapper(message):
        await _handlers.text_handler(message)

    _report_worker = ReportReadyWorker(_pg_repo, _redis_repo, _bot)
    asyncio.create_task(_report_worker.run())

    yield

    if _bot:
        await _bot.close()
    if _redis_repo:
        await _redis_repo.close()
    if _pg_repo:
        await _pg_repo.close()


def create_app():
    from fastapi import FastAPI

    return FastAPI(lifespan=lifespan)


def get_postgres_repo():
    return _pg_repo


def get_redis_repo():
    return _redis_repo


def get_bot():
    return _bot