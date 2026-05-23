"""HTTP handlers for report endpoints."""

from fastapi import APIRouter, HTTPException, Response, Depends
from typing import Optional

from ..domain.models import RFQStatus
from ..domain.repository import PostgreSQLRepository, RedisRepository
from ..services.excel import ExcelGenerator
from ..services.report import ReportService
from ..app.app import get_postgres_repo, get_redis_repo, get_excel_generator
from ..domain.exceptions import RFQNotFoundException

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/{rfq_id}/generate")
async def generate_report(
    rfq_id: int, pg: PostgreSQLRepository = Depends(get_postgres_repo)
):
    """Generate report for RFQ."""
    try:
        excel_gen = ExcelGenerator("./reports")
        report_service = ReportService(pg, excel_gen)
        content = await report_service.generate_report(rfq_id)

        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="rfq_{rfq_id}.xlsx"'
            },
        )
    except RFQNotFoundException as e:
        raise HTTPException(
            status_code=404, detail={"error": str(e), "code": "RFQ_NOT_FOUND"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"error": "Internal error", "code": "INTERNAL"}
        )


@router.get("/{rfq_id}/status")
async def get_report_status(
    rfq_id: int, pg: PostgreSQLRepository = Depends(get_postgres_repo)
):
    """Get processing status for RFQ."""
    status = await pg.get_rfq_status(rfq_id)
    if status.total == 0:
        raise HTTPException(
            status_code=404, detail={"error": "RFQ not found", "code": "RFQ_NOT_FOUND"}
        )
    return status


@router.get("/{rfq_id}/status")
async def get_report_status(
    rfq_id: int, pg: PostgreSQLRepository = Depends(get_postgres_repo)
):
    """Get processing status for RFQ."""
    status = await pg.get_rfq_status(rfq_id)
    if status.total == 0:
        raise HTTPException(
            status_code=404, detail={"error": "RFQ not found", "code": "RFQ_NOT_FOUND"}
        )
    return status


@router.get("/{rfq_id}/file")
async def download_report(
    rfq_id: int, excel_gen: ExcelGenerator = Depends(get_excel_generator)
):
    """Download existing report file."""
    if not excel_gen.file_exists(rfq_id):
        raise HTTPException(
            status_code=404,
            detail={"error": "File not found", "code": "FILE_NOT_FOUND"},
        )

    with open(excel_gen.get_file_path(rfq_id), "rb") as f:
        content = f.read()

    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="rfq_{rfq_id}.xlsx"'},
    )


@router.get("/health")
async def health_check(
    pg: PostgreSQLRepository = Depends(get_postgres_repo),
    redis_repo: RedisRepository = Depends(get_redis_repo),
):
    """Health check endpoint."""
    try:
        # Check DB
        await pg.get_rfq_status(1)  # Simple query

        # Check Redis
        await redis_repo.ping()  # Simple ping

        return {"status": "ok", "db": "ok", "redis": "ok"}
    except Exception as e:
        raise HTTPException(
            status_code=503, detail={"status": "error", "detail": str(e)}
        )
