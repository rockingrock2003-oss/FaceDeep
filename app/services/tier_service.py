from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import User

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


class TierEnforcement:
    def _reset_daily_if_needed(self, user: User) -> bool:
        now = datetime.now(timezone.utc)
        if user.daily_requests_reset_at is None or user.daily_requests_reset_at.date() < now.date():
            user.daily_requests_used = 0
            user.daily_requests_reset_at = now
            return True
        return False

    def _is_plan_active(self, user: User) -> bool:
        if user.plan == "free":
            return True
        if user.plan_expires_at is None:
            return False
        return user.plan_expires_at > datetime.now(timezone.utc)

    def check_limit(self, user: User) -> dict:
        self._reset_daily_if_needed(user)

        if not self._is_plan_active(user):
            return {
                "allowed": False,
                "plan": "free",
                "reason": "Plan expired. Please renew or upgrade.",
                "limit": PLAN_LIMITS["free"],
                "used": user.daily_requests_used,
            }

        limit = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])

        if limit == -1:
            return {
                "allowed": True,
                "plan": user.plan,
                "reason": None,
                "limit": "unlimited",
                "used": user.daily_requests_used,
            }

        if user.daily_requests_used >= limit:
            return {
                "allowed": False,
                "plan": user.plan,
                "reason": f"Daily limit reached ({limit} requests). Upgrade your plan.",
                "limit": limit,
                "used": user.daily_requests_used,
            }

        return {
            "allowed": True,
            "plan": user.plan,
            "reason": None,
            "limit": limit,
            "used": user.daily_requests_used,
            "remaining": limit - user.daily_requests_used,
        }

    def increment_usage(self, user: User):
        self._reset_daily_if_needed(user)
        user.daily_requests_used += 1
        user.number_of_api_use_for_service += 1

    def get_usage_info(self, user: User) -> dict:
        self._reset_daily_if_needed(user)
        limit = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])
        return {
            "plan": user.plan,
            "daily_limit": "unlimited" if limit == -1 else limit,
            "daily_used": user.daily_requests_used,
            "daily_remaining": "unlimited" if limit == -1 else max(0, limit - user.daily_requests_used),
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
            "plan_price": PLAN_PRICES.get(user.plan, 0),
            "plans_available": [
                {"name": "free", "price": 0, "daily_limit": PLAN_LIMITS["free"]},
                {"name": "starter", "price": PLAN_PRICES["starter"], "daily_limit": PLAN_LIMITS["starter"]},
                {"name": "pro", "price": PLAN_PRICES["pro"], "daily_limit": PLAN_LIMITS["pro"]},
                {"name": "enterprise", "price": PLAN_PRICES["enterprise"], "daily_limit": "unlimited"},
            ],
        }

    async def enforce_or_raise(self, db: AsyncSession, user: User):
        result = self.check_limit(user)
        await db.commit()

        if not result["allowed"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": result["reason"],
                    "plan": result["plan"],
                    "limit": result["limit"],
                    "used": result["used"],
                    "upgrade_url": "/api/v1/billing/plans",
                },
            )


tier_enforcement = TierEnforcement()
