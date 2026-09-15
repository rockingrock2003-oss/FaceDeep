import time

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.services.cache import cache

TIER_RPM = {
    "free": 30,
    "starter": 300,
    "pro": 3000,
    "enterprise": 30000,
}

TIER_RPD = {
    "free": settings.FREE_DAILY_LIMIT,
    "starter": settings.STARTER_DAILY_LIMIT,
    "pro": settings.PRO_DAILY_LIMIT,
    "enterprise": settings.ENTERPRISE_DAILY_LIMIT,
}


def _window_key(api_key: str, window: str) -> str:
    return f"rl:{api_key}:{window}"


def _current_minute() -> str:
    return time.strftime("%Y%m%d%H%M", time.gmtime())


def _current_day() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def _next_minute_epoch() -> int:
    now = int(time.time())
    return now + (60 - now % 60)


def _next_day_epoch() -> int:
    now = int(time.time())
    return now + (86400 - now % 86400)


class RateLimiter:
    async def check_and_consume(
        self, api_key: str, plan: str, request: Request
    ) -> dict:
        if not cache.available:
            return {"allowed": True, "rpm_limit": 0, "rpm_remaining": 0, "rpd_limit": 0, "rpd_remaining": 0, "retry_after": 0}

        rpm_limit = TIER_RPM.get(plan, TIER_RPM["free"])
        rpd_limit = TIER_RPD.get(plan, TIER_RPD["free"])

        minute_key = _window_key(api_key, _current_minute())
        day_key = _window_key(api_key, _current_day())

        pipe = cache._client.pipeline()
        pipe.incr(minute_key)
        pipe.expire(minute_key, 120)
        pipe.incr(day_key)
        pipe.expire(day_key, 172800)
        results = await pipe.execute()

        rpm_used = results[0]
        rpd_used = results[2]

        rpm_remaining = max(0, rpm_limit - rpm_used) if rpm_limit > 0 else 999999
        rpd_remaining = max(0, rpd_limit - rpd_used) if rpd_limit > 0 else 999999

        retry_after = 0

        if rpm_limit > 0 and rpm_used > rpm_limit:
            retry_after = 60 - int(time.time()) % 60
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded: {rpm_limit} requests per minute.",
                    "limit": rpm_limit,
                    "used": rpm_used,
                    "window": "minute",
                    "retry_after": retry_after,
                    "plan": plan,
                    "upgrade_url": "/api/v1/billing/plans",
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit-Minute": str(rpm_limit),
                    "X-RateLimit-Remaining-Minute": "0",
                    "X-RateLimit-Reset-Minute": str(_next_minute_epoch()),
                },
            )

        if rpd_limit > 0 and rpd_used > rpd_limit:
            retry_after = _next_day_epoch() - int(time.time())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Daily limit exceeded: {rpd_limit} requests per day.",
                    "limit": rpd_limit,
                    "used": rpd_used,
                    "window": "day",
                    "retry_after": retry_after,
                    "plan": plan,
                    "upgrade_url": "/api/v1/billing/plans",
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit-Day": str(rpd_limit),
                    "X-RateLimit-Remaining-Day": "0",
                    "X-RateLimit-Reset-Day": str(_next_day_epoch()),
                },
            )

        return {
            "allowed": True,
            "rpm_limit": rpm_limit,
            "rpm_remaining": rpm_remaining,
            "rpd_limit": rpd_limit,
            "rpd_remaining": rpd_remaining,
            "retry_after": 0,
        }

    def get_headers(self, result: dict) -> dict[str, str]:
        headers = {}
        if result["rpm_limit"] > 0:
            headers["X-RateLimit-Limit-Minute"] = str(result["rpm_limit"])
            headers["X-RateLimit-Remaining-Minute"] = str(result["rpm_remaining"])
            headers["X-RateLimit-Reset-Minute"] = str(_next_minute_epoch())
        if result["rpd_limit"] > 0:
            headers["X-RateLimit-Limit-Day"] = str(result["rpd_limit"])
            headers["X-RateLimit-Remaining-Day"] = str(result["rpd_remaining"])
            headers["X-RateLimit-Reset-Day"] = str(_next_day_epoch())
        return headers


rate_limiter = RateLimiter()
