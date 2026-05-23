"""Report service orchestrates report generation."""

from typing import List, Dict

from ..domain.exceptions import RFQNotFoundException
from ..domain.models import Item
from ..domain.repository import PostgreSQLRepository
from .excel import ExcelGenerator
from .aggregator import Aggregator


class ReportService:
    """Report service."""

    def __init__(
        self,
        pg: PostgreSQLRepository,
        excel_gen: ExcelGenerator,
        margin_percent: float = 15.0,
    ):
        self.pg = pg
        self.excel_gen = excel_gen
        self.aggregator = Aggregator(margin_percent, pg._pool)

    async def generate_report(self, rfq_id: int) -> bytes:
        """Generate report for RFQ with whatever data is available."""
        items = await self.pg.get_items_by_rfq(rfq_id)
        if not items:
            raise RFQNotFoundException(f"RFQ {rfq_id} not found")

        for item in items:
            if not await self.pg.get_winner(item.id):
                quotes = await self.pg.get_quotes_for_item(item.id)
                winner = await self.aggregator.select_winner(item.id, quotes, item)
                if winner:
                    await self.pg.upsert_winner(
                        item_id=winner.item_id,
                        quote_id=winner.quote_id,
                        final_price=winner.final_price,
                        margin_pct=winner.margin_pct,
                    )

        report_data = await self.pg.get_full_report_data(rfq_id)
        profile = await self.pg.get_user_profile(rfq_id)

        return self.excel_gen.generate(rfq_id, report_data, profile)
