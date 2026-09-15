from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.models.api_request_log import ApiRequestLog

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/usage")
async def usage_analytics(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(UTC) - timedelta(days=days)

    stmt = (
        select(
            func.date(ApiRequestLog.created_at).label("date"),
            func.count().label("total_requests"),
        )
        .where(ApiRequestLog.user_id == user.id)
        .where(ApiRequestLog.created_at >= cutoff)
        .group_by(func.date(ApiRequestLog.created_at))
        .order_by(func.date(ApiRequestLog.created_at))
    )

    result = await db.execute(stmt)
    rows = result.all()

    daily_data = []
    for row in rows:
        daily_data.append({
            "date": str(row.date) if row.date else "unknown",
            "requests": row.total_requests,
        })

    total_requests = sum(d["requests"] for d in daily_data)
    avg_daily = total_requests / days if days > 0 else 0

    return {
        "period_days": days,
        "total_requests": total_requests,
        "average_daily_requests": round(avg_daily, 2),
        "daily_breakdown": daily_data,
    }


@router.get("/endpoints")
async def endpoint_analytics(
    days: int = Query(default=7, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(UTC) - timedelta(days=days)

    stmt = (
        select(
            ApiRequestLog.endpoint,
            func.count().label("count"),
        )
        .where(ApiRequestLog.user_id == user.id)
        .where(ApiRequestLog.created_at >= cutoff)
        .group_by(ApiRequestLog.endpoint)
        .order_by(func.count().desc())
        .limit(20)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return {
        "period_days": days,
        "top_endpoints": [
            {"endpoint": row.endpoint, "count": row.count}
            for row in rows
        ],
    }


@router.get("/cohort")
async def cohort_analysis(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    signup_date = user.created_at
    days_since_signup = (datetime.now(UTC) - signup_date).days if signup_date else 0

    stmt = (
        select(
            func.date(ApiRequestLog.created_at).label("date"),
            func.count().label("requests"),
        )
        .where(ApiRequestLog.user_id == user.id)
        .group_by(func.date(ApiRequestLog.created_at))
        .order_by(func.date(ApiRequestLog.created_at))
    )

    result = await db.execute(stmt)
    rows = result.all()

    return {
        "user_id": user.id,
        "signup_date": signup_date.isoformat() if signup_date else None,
        "days_since_signup": days_since_signup,
        "total_days_active": len(rows),
        "total_requests": sum(r.requests for r in rows),
    }
