"""Quote worker - consumes quote_received stream."""

import asyncio
import logging

from ..domain.models import Quote, Item
from ..domain.repository import PostgreSQLRepository
from ..repository.postgres import PostgresRepository
from ..repository.redis import RedisRepositoryImpl
from ..services.aggregator import Aggregator
from ..services.excel import ExcelGenerator
from ..services.report import ReportService

logger = logging.getLogger(__name__)


class QuoteWorker:
    """Worker that processes quote_received messages."""

    def __init__(
        self,
        pg: PostgreSQLRepository,
        redis_repo: RedisRepositoryImpl,
        aggregator: Aggregator,
        excel_gen: ExcelGenerator,
        report_service: ReportService,
        generation_locks: dict,
        locks_dict_lock: asyncio.Lock,
    ):
        self.pg = pg
        self.redis = redis_repo
        self.aggregator = aggregator
        self.excel_gen = excel_gen
        self.report_service = report_service
        self.generation_locks = generation_locks
        self.locks_dict_lock = locks_dict_lock
        self._running = False

    async def run(self):
        """Main worker loop."""
        await self.redis.create_consumer_group("quote_received", "report-group")
        self._running = True

        logger.info("Quote worker started")

        while self._running:
            try:
                messages = await self.redis.read_quote_received()
                for msg in messages:
                    await self._process_message(msg)
            except Exception as e:
                logger.exception(f"Error processing messages: {e}")

            await asyncio.sleep(1)

    async def _process_message(self, msg: dict):
        """Process single message."""
        try:
            data = msg["data"]
            message_id = msg["id"]

            # Parse fields
            item_id = int(data.get("item_id", 0))
            supplier_id = int(data.get("supplier_id", 0))
            supplier_email = data.get("supplier_email", "")
            price_str = data.get("price", "0")
            delivery_days_str = data.get("delivery_days", "0")
            pickup_address = data.get("pickup_address")
            source = data.get("source", "email")

            # Parse price and days
            try:
                price = float(price_str)
            except ValueError:
                logger.warning(f"Invalid price: {price_str}")
                await self.redis.ack_quote("quote_received", "report-group", message_id)
                return

            try:
                delivery_days = int(delivery_days_str)
            except ValueError:
                logger.warning(f"Invalid delivery_days: {delivery_days_str}")
                await self.redis.ack_quote("quote_received", "report-group", message_id)
                return

            # Validate
            if price <= 0 or price > 100_000_000:
                logger.warning(f"Price out of range: {price}")
                await self.redis.ack_quote("quote_received", "report-group", message_id)
                return

            if delivery_days < 0 or delivery_days > 730:
                logger.warning(f"Delivery days out of range: {delivery_days}")
                await self.redis.ack_quote("quote_received", "report-group", message_id)
                return

            # Get item for deadline check
            item = await self.pg.get_item(item_id)
            if not item:
                logger.warning(f"Item not found: {item_id}")
                await self.redis.ack_quote("quote_received", "report-group", message_id)
                return

            # Upsert quote
            quote = await self.pg.upsert_quote(
                item_id=item_id,
                supplier_id=supplier_id,
                supplier_email=supplier_email,
                price=price,
                delivery_days=delivery_days,
                pickup_address=pickup_address,
                source=source,
            )

            logger.info(
                f"Quote saved: item={item_id}, supplier={supplier_id}, price={price}"
            )

            # Recalculate winner
            quotes = await self.pg.get_quotes_for_item(item_id)
            winner = await self.aggregator.select_winner(item_id, quotes, item)
            if winner:
                saved_winner = await self.pg.upsert_winner(
                    item_id=winner.item_id,
                    quote_id=winner.quote_id,
                    final_price=winner.final_price,
                    margin_pct=winner.margin_pct,
                )
                logger.info(
                    f"Winner updated: item={item_id}, quote_id={saved_winner.quote_id}, final_price={saved_winner.final_price}"
                )

                # Check if RFQ is complete
                if await self.pg.is_rfq_complete(item.rfq_id):
                    if not self.excel_gen.file_exists(item.rfq_id):
                        # Acquire lock for this RFQ to prevent concurrent report generation
                        async with await self._get_generation_lock(item.rfq_id):
                            await self._generate_and_publish_report(item.rfq_id)
                else:
                    logger.info(f"RFQ {item.rfq_id} not complete yet")

            # Acknowledge
            await self.redis.ack_quote("quote_received", "report-group", message_id)

        except Exception as e:
            logger.exception(f"Failed to process message: {e}")

    async def _get_generation_lock(self, rfq_id: int) -> asyncio.Lock:
        """Get lock for specific RFQ."""
        async with self.locks_dict_lock:
            if rfq_id not in self.generation_locks:
                self.generation_locks[rfq_id] = asyncio.Lock()
            return self.generation_locks[rfq_id]

    async def _generate_and_publish_report(self, rfq_id: int):
        """Generate report and publish event."""
        try:
            content = await self.report_service.generate_report(rfq_id)
            file_key = f"reports/rfq_{rfq_id}.xlsx"

            # Save file
            self.excel_gen.save(rfq_id, content)

            # Publish event
            await self.redis.publish_report_ready(rfq_id, file_key)
            logger.info(f"Report ready published: rfq_id={rfq_id}")
        except Exception as e:
            logger.exception(f"Failed to generate report: {e}")

    def stop(self):
        """Stop worker."""
        self._running = False
