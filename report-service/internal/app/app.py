"""Application factory and dependency injection."""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from internal.config.config import get_settings
from internal.domain.repository import PostgreSQLRepository, RedisRepository
from internal.repository.postgres import PostgresRepository
from internal.repository.redis import RedisRepositoryImpl
from internal.services.aggregator import Aggregator
from internal.services.excel import ExcelGenerator
from internal.services.report import ReportService
from internal.workers.quote_worker import QuoteWorker


# Global instances
_pg_repo: PostgresRepository = None
_redis_repo: RedisRepositoryImpl = None
_quote_worker: QuoteWorker = None
_excel_gen: ExcelGenerator = None
_report_service: ReportService = None
_overdue_task: asyncio.Task = None
_generation_locks: Dict[int, asyncio.Lock] = {}
_locks_dict_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global \
        _pg_repo, \
        _redis_repo, \
        _quote_worker, \
        _excel_gen, \
        _report_service, \
        _overdue_task

    settings = get_settings()

    # Initialize repositories
    _pg_repo = PostgresRepository(settings.db_dsn)
    await _pg_repo.connect()

    _redis_repo = RedisRepositoryImpl(settings.redis_url)
    await _redis_repo.connect()

    # Initialize services
    aggregator = Aggregator(settings.margin_percent, _pg_repo._pool)
    _excel_gen = ExcelGenerator(settings.report_dir)
    _report_service = ReportService(_pg_repo, _excel_gen, settings.margin_percent)

    # Start quote worker with shared services
    _quote_worker = QuoteWorker(
        _pg_repo,
        _redis_repo,
        aggregator,
        _excel_gen,
        _report_service,
        _generation_locks,
        _locks_dict_lock,
    )
    asyncio.create_task(_quote_worker.run())

    # Start overdue checker in lifespan (single instance)
    async def periodic_overdue_check():
        while True:
            try:
                await asyncio.sleep(600)  # 10 minutes
                await _check_overdue_rfqs()
            except Exception as e:
                print(f"Overdue check error: {e}")

    _overdue_task = asyncio.create_task(periodic_overdue_check())

    yield

    # Shutdown
    if _quote_worker:
        _quote_worker.stop()
    if _overdue_task:
        _overdue_task.cancel()
    if _redis_repo:
        await _redis_repo.close()
    if _pg_repo:
        await _pg_repo.close()


async def _check_overdue_rfqs():
    """Check for overdue RFQs and generate reports."""
    overdue_rfq_ids = await _pg_repo.get_overdue_rfqs()
    for rfq_id in overdue_rfq_ids:
        # Skip if report already exists
        if _excel_gen.file_exists(rfq_id):
            continue
        print(f"Generating overdue report for RFQ {rfq_id}")
        try:
            content = await _report_service.generate_report(rfq_id)
            file_key = f"reports/rfq_{rfq_id}.xlsx"
            _excel_gen.save(rfq_id, content)
            await _redis_repo.publish_report_ready(rfq_id, file_key)
            print(f"Overdue report generated: rfq_id={rfq_id}")
        except Exception as e:
            print(f"Failed to generate overdue report for RFQ {rfq_id}: {e}")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="Report Service",
        description="Service for processing quotes and generating reports",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from internal.handlers.report import router as report_router

    # Mount health without prefix
    from internal.handlers.report import health_check

    app.add_api_route("/health", health_check, methods=["GET"], tags=["health"])

    app.include_router(report_router)

    return app


# Dependency injection helpers
def get_postgres_repo() -> PostgreSQLRepository:
    """Get PostgreSQL repository."""
    return _pg_repo


def get_redis_repo() -> RedisRepository:
    """Get Redis repository."""
    return _redis_repo


def get_excel_generator() -> ExcelGenerator:
    """Get Excel generator."""
    return _excel_gen


def get_report_service() -> ReportService:
    """Get report service."""
    return _report_service


async def get_generation_lock(rfq_id: int) -> asyncio.Lock:
    """Get lock for specific RFQ to prevent concurrent generation."""
    async with _locks_dict_lock:
        if rfq_id not in _generation_locks:
            _generation_locks[rfq_id] = asyncio.Lock()
        return _generation_locks[rfq_id]
