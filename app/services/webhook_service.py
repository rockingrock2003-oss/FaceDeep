import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.webhook import WebhookDelivery, WebhookSubscription

logger = logging.getLogger("facedeep.webhooks")

RETRY_DELAYS = [60, 300, 1800]  # 1min, 5min, 30min


def generate_webhook_secret() -> str:
    import secrets
    return secrets.token_hex(32)


def compute_signature(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


class WebhookService:
    async def dispatch_event(self, user_id: str, event: str, data: dict):
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(WebhookSubscription).where(
                    WebhookSubscription.user_id == user_id,
                    WebhookSubscription.is_active == True,
                )
                result = await db.execute(stmt)
                subs = result.scalars().all()

                for sub in subs:
                    subscribed_events = json.loads(sub.events)
                    if event not in subscribed_events and "*" not in subscribed_events:
                        continue
                    await self._deliver(db, sub, event, data)
        except Exception as e:
            logger.error(f"Webhook dispatch error: {e}")

    async def _deliver(self, db: AsyncSession, sub: WebhookSubscription, event: str, data: dict):
        payload = json.dumps({"event": event, "data": data, "timestamp": datetime.now(UTC).isoformat()}).encode()
        signature = compute_signature(payload, sub.secret)

        delivery = WebhookDelivery(
            subscription_id=sub.id,
            event=event,
            payload=payload.decode(),
            status="pending",
            attempts=0,
            max_attempts=3,
        )
        db.add(delivery)
        await db.flush()

        success = await self._send_request(sub.url, payload, signature, delivery)
        if success:
            delivery.status = "success"
            delivery.delivered_at = datetime.now(UTC)
        else:
            delivery.status = "failed"
            if delivery.attempts < delivery.max_attempts:
                delay = RETRY_DELAYS[min(delivery.attempts, len(RETRY_DELAYS) - 1)]
                delivery.next_retry_at = datetime.now(UTC).replace(
                    second=datetime.now(UTC).second + delay
                )
        await db.commit()

    async def _send_request(self, url: str, payload: bytes, signature: str, delivery: WebhookDelivery) -> bool:
        delivery.attempts += 1
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    content=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": f"sha256={signature}",
                        "X-Webhook-Event": delivery.event,
                        "User-Agent": "FaceDeep-Webhook/1.0",
                    },
                )
                delivery.status_code = resp.status_code
                delivery.response_body = resp.text[:2000]
                return 200 <= resp.status_code < 300
        except Exception as e:
            delivery.response_body = str(e)[:2000]
            logger.error(f"Webhook delivery failed: {e}")
            return False

    async def retry_pending(self):
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.now(UTC)
                stmt = select(WebhookDelivery).where(
                    WebhookDelivery.status == "failed",
                    WebhookDelivery.next_retry_at <= now,
                    WebhookDelivery.attempts < WebhookDelivery.max_attempts,
                )
                result = await db.execute(stmt)
                deliveries = result.scalars().all()

                for delivery in deliveries:
                    sub_stmt = select(WebhookSubscription).where(
                        WebhookSubscription.id == delivery.subscription_id
                    )
                    sub_result = await db.execute(sub_stmt)
                    sub = sub_result.scalar_one_or_none()
                    if not sub or not sub.is_active:
                        delivery.status = "skipped"
                        continue

                    payload = delivery.payload.encode()
                    sig = compute_signature(payload, sub.secret)
                    success = await self._send_request(sub.url, payload, sig, delivery)
                    if success:
                        delivery.status = "success"
                        delivery.delivered_at = now
                    elif delivery.attempts >= delivery.max_attempts:
                        delivery.status = "failed"
                    else:
                        delay = RETRY_DELAYS[min(delivery.attempts - 1, len(RETRY_DELAYS) - 1)]
                        delivery.next_retry_at = now.replace(second=now.second + delay)

                await db.commit()
        except Exception as e:
            logger.error(f"Webhook retry error: {e}")


webhook_service = WebhookService()
