import platform
import time

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import metrics
from app.core.security import get_current_user
from app.db import get_db
from app.models import User

router = APIRouter(tags=["Observability"])

_start_time = time.time()


@router.get("/health", tags=["Health"])
async def health_check():
    from app.services.cache import cache
    from app.services.worker import worker_pool

    redis_ok = cache.available
    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "FaceDeep API",
        "version": settings.API_LATEST_VERSION,
        "redis": "connected" if redis_ok else "unavailable",
        "workers": worker_pool.stats,
    }


@router.get("/ready")
async def readiness_check():
    from app.services.cache import cache

    checks = {
        "database": "ok",
        "redis": "connected" if cache.available else "unavailable",
    }
    healthy = True
    return {
        "status": "ready" if healthy else "not_ready",
        "checks": checks,
    }


@router.get("/startup")
async def startup_check():
    uptime = round(time.time() - _start_time, 2)
    return {
        "status": "started",
        "uptime_seconds": uptime,
        "python_version": platform.python_version(),
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    return PlainTextResponse(
        content=metrics.to_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.post("/cleanup-retention")
async def cleanup_retention(
    user: User = Depends(get_current_user),
):
    if user.plan not in ("pro", "enterprise"):
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data retention cleanup requires Pro or Enterprise plan",
        )

    from app.services.retention import retention_service

    result = await retention_service.run_full_cleanup()
    return result
