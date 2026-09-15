import logging
import time
from datetime import UTC, datetime

from app.db import AsyncSessionLocal
from app.models import User
from app.services.cache import cache

logger = logging.getLogger("facedeep.metering")

ENDPOINT_COSTS = {
    "/face/recognize": 0.01,
    "/face/ismatch": 0.005,
    "/face/enroll": 0.005,
    "/face/bulk-enroll": 0.005,
    "/face/delete": 0.0,
}

USAGE_THRESHOLDS = [0.80, 0.90, 1.00]


class MeteringService:
    async def record_request(self, user_id: str, endpoint: str, response_time_ms: float):
        cost = ENDPOINT_COSTS.get(endpoint, 0.001)

        minute_key = f"meter:{user_id}:rpm:{time.strftime('%Y%m%d%H%M', time.gmtime())}"
        day_key = f"meter:{user_id}:rpd:{time.strftime('%Y%m%d', time.gmtime())}"
        cost_key = f"meter:{user_id}:cost:{time.strftime('%Y%m', time.gmtime())}"

        pipe = cache._client.pipeline()
        pipe.incr(minute_key)
        pipe.expire(minute_key, 120)
        pipe.incr(day_key)
        pipe.expire(day_key, 172800)
        pipe.incrbyfloat(cost_key, cost)
        pipe.expire(cost_key, 7776000)
        await pipe.execute()

        await self._check_usage_alerts(user_id)

    async def _check_usage_alerts(self, user_id: str):
        try:
            day_key = f"meter:{user_id}:rpd:{time.strftime('%Y%m%d', time.gmtime())}"
            used = await cache.get_counter(day_key)

            async with AsyncSessionLocal() as db:
                from sqlalchemy import select

                stmt = select(User).where(User.id == user_id)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                if not user:
                    return

                from app.services.tier_service import PLAN_LIMITS

                limit = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])
                if limit <= 0:
                    return

                ratio = used / limit

                for threshold in USAGE_THRESHOLDS:
                    alert_key = f"alert:{user_id}:{threshold}:{time.strftime('%Y%m%d')}"
                    already_sent = await cache.get(alert_key)
                    if already_sent:
                        continue

                    if ratio >= threshold:
                        await cache.set(alert_key, 1, ttl=86400)
                        await self._send_usage_alert(user, used, limit, threshold)

        except Exception as e:
            logger.warning(f"Usage alert check failed: {e}")

    async def _send_usage_alert(self, user, used: int, limit: int, threshold: float):
        pct = int(threshold * 100)
        logger.info(
            f"Usage alert: user={user.id} plan={user.plan} "
            f"used={used}/{limit} ({pct}%)"
        )
        try:
            from app.services.webhook_service import webhook_service

            await webhook_service.dispatch_event(
                user.id,
                "billing.alert",
                {
                    "type": "usage_threshold",
                    "threshold_percent": pct,
                    "used": used,
                    "limit": limit,
                    "plan": user.plan,
                },
            )
        except Exception:
            pass

    async def get_monthly_cost(self, user_id: str) -> float:
        cost_key = f"meter:{user_id}:cost:{time.strftime('%Y%m', time.gmtime())}"
        val = await cache.get(cost_key)
        return float(val) if val else 0.0

    async def get_realtime_usage(self, user_id: str) -> dict:
        minute_key = f"meter:{user_id}:rpm:{time.strftime('%Y%m%d%H%M', time.gmtime())}"
        day_key = f"meter:{user_id}:rpd:{time.strftime('%Y%m%d', time.gmtime())}"
        cost = await self.get_monthly_cost(user_id)

        return {
            "requests_this_minute": await cache.get_counter(minute_key),
            "requests_today": await cache.get_counter(day_key),
            "cost_this_month": round(cost, 4),
        }


metering_service = MeteringService()
