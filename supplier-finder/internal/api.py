"""Health check API for supplier-finder."""

import logging
from fastapi import FastAPI, HTTPException
import asyncpg
import redis.asyncio as redis
from .config.config import get_settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Supplier Finder", version="1.0.0")


@app.get("/health")
async def health_check():
    """Check service health."""
    try:
        settings = get_settings()
        
        # Test DB connection
        conn = await asyncpg.connect(settings.db_dsn)
        await conn.close()
        
        # Test Redis connection
        r = redis.from_url(settings.redis_url)
        await r.ping()
        await r.close()
        
        return {"status": "ok", "db": "ok", "redis": "ok"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail={"status": "error", "detail": str(e)})


@app.get("/stats")
async def stats():
    """Return database statistics."""
    try:
        settings = get_settings()
        from ..utils.db import get_stats
        conn = await asyncpg.connect(settings.db_dsn)
        stats = await get_stats(conn)
        await conn.close()
        return stats
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
