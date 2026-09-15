import logging
import time
from datetime import UTC, datetime, timedelta

from app.db import AsyncSessionLocal
from app.models.api_request_log import ApiRequestLog

logger = logging.getLogger("facedeep.retention")

DEFAULT_RETENTION_DAYS = 90


class RetentionService:
    async def cleanup_old_logs(self, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.now(UTC) - timedelta(days=retention_days)

                from sqlalchemy import delete

                stmt = delete(ApiRequestLog).where(
                    ApiRequestLog.created_at < cutoff
                )
                result = await db.execute(stmt)
                deleted = result.rowcount
                await db.commit()

                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} API request logs older than {retention_days} days")
                return deleted
        except Exception as e:
            logger.error(f"Retention cleanup failed: {e}")
            return 0

    async def cleanup_old_webhook_deliveries(self, retention_days: int = 30) -> int:
        try:
            from app.models.webhook import WebhookDelivery

            async with AsyncSessionLocal() as db:
                cutoff = datetime.now(UTC) - timedelta(days=retention_days)

                from sqlalchemy import delete

                stmt = delete(WebhookDelivery).where(
                    WebhookDelivery.created_at < cutoff
                )
                result = await db.execute(stmt)
                deleted = result.rowcount
                await db.commit()

                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} webhook deliveries older than {retention_days} days")
                return deleted
        except Exception as e:
            logger.error(f"Webhook delivery cleanup failed: {e}")
            return 0

    async def run_full_cleanup(self) -> dict:
        logs_deleted = await self.cleanup_old_logs(90)
        deliveries_deleted = await self.cleanup_old_webhook_deliveries(30)
        return {
            "logs_deleted": logs_deleted,
            "webhook_deliveries_deleted": deliveries_deleted,
            "timestamp": datetime.now(UTC).isoformat(),
        }


retention_service = RetentionService()
