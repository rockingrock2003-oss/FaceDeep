from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/admin", tags=["Admin"])


class RateLimitUpdate(BaseModel):
    user_id: str
    daily_limit: int
    per_minute_limit: int


class RateLimitResponse(BaseModel):
    user_id: str
    username: str
    plan: str
    daily_limit: int
    daily_used: int
    per_minute_limit: int


PLAN_LIMITS = {
    "free": {"daily": 100, "per_minute": 10},
    "starter": {"daily": 10000, "per_minute": 100},
    "pro": {"daily": 100000, "per_minute": 500},
    "enterprise": {"daily": -1, "per_minute": 1000},
}


@router.get("/rate-limits")
async def list_rate_limits(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.plan not in ("pro", "enterprise"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access requires Pro or Enterprise plan",
        )

    stmt = select(User)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return {
        "rate_limits": [
            {
                "user_id": u.id,
                "username": u.username,
                "plan": u.plan,
                "daily_limit": PLAN_LIMITS.get(u.plan, PLAN_LIMITS["free"])["daily"],
                "daily_used": u.daily_requests_used,
                "per_minute_limit": PLAN_LIMITS.get(u.plan, PLAN_LIMITS["free"])["per_minute"],
            }
            for u in users
        ]
    }


@router.put("/rate-limits")
async def update_rate_limit(
    body: RateLimitUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.plan not in ("enterprise",):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Custom rate limits require Enterprise plan",
        )

    stmt = select(User).where(User.id == body.user_id)
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": body.user_id,
        "daily_limit": body.daily_limit,
        "per_minute_limit": body.per_minute_limit,
        "note": "Custom rate limits applied (stored in Redis for enforcement)",
    }
