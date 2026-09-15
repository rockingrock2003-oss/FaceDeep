import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.models.webhook import WebhookDelivery, WebhookSubscription
from app.schemas.webhook import (
    WebhookDeliveryResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionResponse,
    WebhookSubscriptionUpdate,
    WebhookTestResponse,
)
from app.services.webhook_service import generate_webhook_secret, webhook_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

SUPPORTED_EVENTS = [
    "bulk-import.completed",
    "recognition.event",
    "billing.alert",
    "face.enrolled",
    "face.deleted",
    "*",
]


@router.post("", response_model=WebhookSubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invalid = [e for e in body.events if e not in SUPPORTED_EVENTS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid events: {invalid}")

    if not body.url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Webhook URL must use HTTPS")

    secret = generate_webhook_secret()
    sub = WebhookSubscription(
        user_id=current_user.id,
        url=body.url,
        events=json.dumps(body.events),
        secret=secret,
    )
    db.add(sub)
    await db.flush()
    await db.commit()

    return WebhookSubscriptionResponse(
        id=sub.id,
        url=sub.url,
        events=json.loads(sub.events),
        is_active=sub.is_active,
        secret=secret,
        created_at=sub.created_at.isoformat(),
    )


@router.get("", response_model=list[WebhookSubscriptionResponse])
async def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebhookSubscription).where(WebhookSubscription.user_id == current_user.id)
    result = await db.execute(stmt)
    subs = result.scalars().all()
    return [
        WebhookSubscriptionResponse(
            id=s.id,
            url=s.url,
            events=json.loads(s.events),
            is_active=s.is_active,
            created_at=s.created_at.isoformat(),
        )
        for s in subs
    ]


@router.get("/{webhook_id}", response_model=WebhookSubscriptionResponse)
async def get_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return WebhookSubscriptionResponse(
        id=sub.id,
        url=sub.url,
        events=json.loads(sub.events),
        is_active=sub.is_active,
        created_at=sub.created_at.isoformat(),
    )


@router.put("/{webhook_id}", response_model=WebhookSubscriptionResponse)
async def update_webhook(
    webhook_id: str,
    body: WebhookSubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if body.url is not None:
        if not body.url.startswith("https://"):
            raise HTTPException(status_code=400, detail="Webhook URL must use HTTPS")
        sub.url = body.url
    if body.events is not None:
        invalid = [e for e in body.events if e not in SUPPORTED_EVENTS]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid events: {invalid}")
        sub.events = json.dumps(body.events)
    if body.is_active is not None:
        sub.is_active = body.is_active

    await db.commit()
    return WebhookSubscriptionResponse(
        id=sub.id,
        url=sub.url,
        events=json.loads(sub.events),
        is_active=sub.is_active,
        created_at=sub.created_at.isoformat(),
    )


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    await db.delete(sub)
    await db.commit()
    return {"status": "success", "message": "Webhook deleted"}


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id,
    )
    sub_result = await db.execute(sub_stmt)
    sub = sub_result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    stmt = (
        select(WebhookDelivery)
        .where(WebhookDelivery.subscription_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    deliveries = result.scalars().all()

    return [
        WebhookDeliveryResponse(
            id=d.id,
            event=d.event,
            status=d.status,
            status_code=d.status_code,
            attempts=d.attempts,
            max_attempts=d.max_attempts,
            created_at=d.created_at.isoformat(),
            delivered_at=d.delivered_at.isoformat() if d.delivered_at else None,
        )
        for d in deliveries
    ]


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    await webhook_service.dispatch_event(current_user.id, "webhook.test", {
        "message": "Test webhook delivery",
        "webhook_id": sub.id,
    })

    return WebhookTestResponse(
        status="success",
        message="Test event dispatched. Check delivery logs.",
    )
