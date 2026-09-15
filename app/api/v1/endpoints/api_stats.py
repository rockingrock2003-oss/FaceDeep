from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user as _get_user
from app.db import get_db
from app.models import User
from app.models.api_request_log import ApiRequestLog
from app.services.cache import cache

router = APIRouter(prefix="/auth", tags=["API Stats"])

TRACKED_ENDPOINTS = [
    "/api/v1/face/recognize",
    "/api/v1/face/ismatch",
    "/api/v1/face/delete",
    "/api/v1/face/enroll",
    "/api/v1/face/bulk-enroll",
]

ENDPOINT_COSTS = {
    "/api/v1/face/recognize": 0.01,
    "/api/v1/face/ismatch": 0.005,
    "/api/v1/face/enroll": 0.005,
    "/api/v1/face/bulk-enroll": 0.005,
    "/api/v1/face/delete": 0.0,
}

PLAN_LIMITS = {
    "free": settings.FREE_DAILY_LIMIT,
    "starter": settings.STARTER_DAILY_LIMIT,
    "pro": settings.PRO_DAILY_LIMIT,
    "enterprise": settings.ENTERPRISE_DAILY_LIMIT,
}

PLAN_PRICES = {
    "free": 0.0,
    "starter": settings.STARTER_PRICE,
    "pro": settings.PRO_PRICE,
    "enterprise": settings.ENTERPRISE_PRICE,
}


def _local_time(utc_dt: datetime) -> str:
    return utc_dt.strftime("%Y-%m-%d %H:%M:%S")


def _local_time_short(utc_dt: datetime) -> str:
    return utc_dt.strftime("%H:%M:%S")


@router.get("/api-stats")
async def get_api_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_user),
):
    cache_key = f"stats:{current_user.id}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    now = datetime.now(UTC)
    one_year_ago = now - timedelta(days=365)

    result = await db.execute(
        select(
            ApiRequestLog.endpoint,
            ApiRequestLog.response_time_ms,
            ApiRequestLog.created_at,
        )
        .where(
            ApiRequestLog.user_id == current_user.id,
            ApiRequestLog.created_at >= one_year_ago,
            ApiRequestLog.endpoint.in_(TRACKED_ENDPOINTS),
        )
        .order_by(ApiRequestLog.created_at.asc())
    )
    rows = result.all()

    requests = []
    for row in rows:
        requests.append({
            "endpoint": _ep_label(row.endpoint),
            "response_time_ms": round(row.response_time_ms, 2),
            "created_at": row.created_at.isoformat(),
        })

    today_key = now.strftime("%Y-%m-%d")
    this_month_key = now.strftime("%Y-%m")

    daily_agg: dict[str, dict] = {}
    monthly_agg: dict[str, dict] = {}
    yearly_agg: dict[str, dict] = {}

    for row in rows:
        label = _ep_label(row.endpoint)
        ms = row.response_time_ms
        day_key = row.created_at.strftime("%Y-%m-%d")
        month_key = row.created_at.strftime("%Y-%m")

        for agg in [daily_agg, monthly_agg, yearly_agg]:
            key = day_key if agg is daily_agg else month_key if agg is monthly_agg else month_key
            if key not in agg:
                agg[key] = {}
            if label not in agg[key]:
                agg[key][label] = {"total_ms": 0.0, "count": 0}
            agg[key][label]["total_ms"] += ms
            agg[key][label]["count"] += 1

    daily_avg = _build_chart(daily_agg, daily=True)
    monthly_avg = _build_chart(monthly_agg)
    yearly_avg = _build_chart(yearly_agg)

    today_stats: dict[str, dict] = {}
    for row in rows:
        if row.created_at.strftime("%Y-%m-%d") == today_key:
            label = _ep_label(row.endpoint)
            if label not in today_stats:
                today_stats[label] = {"total_ms": 0.0, "count": 0}
            today_stats[label]["total_ms"] += row.response_time_ms
            today_stats[label]["count"] += 1

    month_stats: dict[str, dict] = {}
    for row in rows:
        if row.created_at.strftime("%Y-%m") == this_month_key:
            label = _ep_label(row.endpoint)
            if label not in month_stats:
                month_stats[label] = {"total_ms": 0.0, "count": 0}
            month_stats[label]["total_ms"] += row.response_time_ms
            month_stats[label]["count"] += 1

    year_stats: dict[str, dict] = {}
    for row in rows:
        label = _ep_label(row.endpoint)
        if label not in year_stats:
            year_stats[label] = {"total_ms": 0.0, "count": 0}
        year_stats[label]["total_ms"] += row.response_time_ms
        year_stats[label]["count"] += 1

    def _avg(stats: dict, label: str) -> float:
        if label in stats and stats[label]["count"] > 0:
            return round(stats[label]["total_ms"] / stats[label]["count"], 2)
        return 0

    def _overall_avg(stats: dict) -> float:
        total_ms = sum(v["total_ms"] for v in stats.values())
        total_count = sum(v["count"] for v in stats.values())
        return round(total_ms / total_count, 2) if total_count > 0 else 0

    summary = {
        "today": {
            "Recognize": _avg(today_stats, "Recognize"),
            "Add": _avg(today_stats, "Add"),
            "Delete": _avg(today_stats, "Delete"),
            "IsMatch": _avg(today_stats, "IsMatch"),
            "overall": _overall_avg(today_stats),
        },
        "this_month": {
            "Recognize": _avg(month_stats, "Recognize"),
            "Add": _avg(month_stats, "Add"),
            "Delete": _avg(month_stats, "Delete"),
            "IsMatch": _avg(month_stats, "IsMatch"),
            "overall": _overall_avg(month_stats),
        },
        "this_year": {
            "Recognize": _avg(year_stats, "Recognize"),
            "Add": _avg(year_stats, "Add"),
            "Delete": _avg(year_stats, "Delete"),
            "IsMatch": _avg(year_stats, "IsMatch"),
            "overall": _overall_avg(year_stats),
        },
    }

    plan = current_user.plan
    daily_limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    daily_used = current_user.daily_requests_used
    daily_remaining = "unlimited" if daily_limit == -1 else max(0, daily_limit - daily_used)
    plan_price = PLAN_PRICES.get(plan, 0)
    plan_expires = current_user.plan_expires_at.isoformat() if current_user.plan_expires_at else None

    total_count = len(rows)
    total_cost = round(sum(ENDPOINT_COSTS.get(row.endpoint, 0) for row in rows), 4)

    response = {
        "requests": requests,
        "daily_avg": daily_avg,
        "monthly": monthly_avg,
        "yearly": yearly_avg,
        "summary": summary,
        "billing": {
            "plan": plan,
            "daily_limit": daily_limit,
            "daily_used": daily_used,
            "daily_remaining": daily_remaining,
            "plan_price": plan_price,
            "plan_expires_at": plan_expires,
            "total_requests": total_count,
            "total_cost": total_cost,
        },
    }

    await cache.set(cache_key, response, ttl=60)
    return response


def _build_chart(agg: dict, daily: bool = False) -> list[dict]:
    chart = []
    for key in sorted(agg.keys()):
        entry = {"date": key}
        total_ms = 0.0
        total_count = 0
        for label in ["Recognize", "Add", "Delete", "IsMatch"]:
            if label in agg[key]:
                d = agg[key][label]
                entry[f"{label}_avg"] = round(d["total_ms"] / d["count"], 2)
                entry[f"{label}_count"] = d["count"]
                total_ms += d["total_ms"]
                total_count += d["count"]
            else:
                entry[f"{label}_avg"] = None
                entry[f"{label}_count"] = 0
        entry["overall_avg"] = round(total_ms / total_count, 2) if total_count > 0 else 0
        entry["total_count"] = total_count
        chart.append(entry)
    return chart


def _ep_label(ep: str) -> str:
    return {
        "/api/v1/face/recognize": "Recognize",
        "/api/v1/face/enroll": "Add",
        "/api/v1/face/bulk-enroll": "Add",
        "/api/v1/face/delete": "Delete",
        "/api/v1/face/ismatch": "IsMatch",
    }.get(ep, ep)
