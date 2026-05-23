"""Report ready worker — sends final report with UX guidelines."""

import logging
import httpx

from vkbottle import Bot

from ..config.config import get_settings
from ..repository.postgres import PostgresRepository
from ..repository.redis import RedisRepositoryImpl

logger = logging.getLogger(__name__)


class ReportReadyWorker:
    def __init__(
        self, pg: PostgresRepository, redis_repo: RedisRepositoryImpl, bot: Bot
    ):
        self.pg = pg
        self.redis = redis_repo
        self.bot = bot

    async def run(self):
        await self.redis.subscribe_report_ready(self._on_report_ready)
        logger.info("Report ready worker started")

    async def _on_report_ready(self, data: dict):
        try:
            rfq_id = int(data.get("rfq_id", 0))

            rfq = await self.pg.get_rfq_by_id(rfq_id)
            if not rfq:
                logger.warning(f"RFQ {rfq_id} not found")
                return

            creator_vk_id = rfq.get("created_by_vk")
            if not creator_vk_id:
                logger.warning(f"RFQ {rfq_id} has no creator_vk_id")
                return

            status = await self.pg.get_rfq_status(rfq_id)
            items_status = await self.pg.get_rfq_items_status(rfq_id)
            suppliers = await self.pg.get_rfq_supplier_summary(rfq_id)

            report_msg = self._build_summary(rfq_id, status, items_status, suppliers)

            await self.bot.api.messages.send(
                peer_id=creator_vk_id,
                message=report_msg,
                random_id=0,
            )

            settings = get_settings()
            report_url = f"{settings.report_service_url}/report/{rfq_id}/file"
            async with httpx.AsyncClient() as client:
                resp = await client.get(report_url)
                resp.raise_for_status()
                file_bytes = resp.content

            upload_resp = await self.bot.api.docs.get_messages_upload_server(
                type="doc", peer_id=creator_vk_id
            )
            async with httpx.AsyncClient() as client:
                upload = await client.post(
                    upload_resp.upload_url,
                    files={
                        "file": (
                            "report.xlsx",
                            file_bytes,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    },
                )
                upload_data = upload.json()

            file_param = upload_data.get("file")
            if not file_param:
                logger.warning(f"No 'file' in upload response: {upload_data}")
                return

            doc = await self.bot.api.docs.save(
                file=file_param, title=f"report_{rfq_id}.xlsx"
            )

            await self.bot.api.messages.send(
                peer_id=creator_vk_id,
                message=f"📄 Отчёт: report_{rfq_id}.xlsx",
                attachment=f"doc{doc.doc.owner_id}_{doc.doc.id}",
                random_id=0,
            )

            logger.info(
                f"Report sent to VK user {creator_vk_id} for RFQ {rfq_id}"
            )

        except Exception as e:
            logger.exception(f"Error processing report_ready: {e}")

    def _build_summary(
        self, rfq_id: int, status: dict, items_status: list, suppliers: list
    ) -> str:
        lines = [f"📋 **Обновление статуса заявки #{rfq_id}**", ""]

        quoted = [i for i in items_status if i["quote_count"] > 0]
        winners = [i for i in items_status if i["winner_count"] > 0]
        lines.append(f"• {status['total']} позиций")
        lines.append(f"• {status['quoted']} с котировками")
        lines.append(f"• {status['winners']} победителей")
        if suppliers:
            lines.append(f"• {len(suppliers)} поставщиков участвовало")

        if quoted:
            prices = [i["min_price"] for i in quoted if i.get("min_price")]
            if prices:
                total = sum(prices)
                lines.append("")
                lines.append(f"💰 Сумма минимальных цен: {total:,.2f}")

        if len(quoted) > 0 and status["total"] > 0:
            pct = int(len(quoted) / status["total"] * 100)
            if pct < 100:
                lines.append(f"📩 Охват котировками: {pct}%")

        if winners:
            lines.append(f"🏆 Победители определены по {len(winners)} позициям")

        return "\n".join(lines)
