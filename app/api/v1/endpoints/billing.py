from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.billing import (
    PlanInfoResponse,
    UsageResponse,
    WebhookResponse,
)
from app.services.tier_service import tier_enforcement

router = APIRouter(prefix="/billing", tags=["Billing & Payments"])


@router.get("/plans", response_model=PlanInfoResponse)
async def get_plans():
    return PlanInfoResponse(
        plans=[
            {
                "name": "free",
                "price": 0,
                "daily_limit": settings.FREE_DAILY_LIMIT,
                "features": ["100 requests/day", "1 user", "Email support"],
                "payment_link": None,
            },
            {
                "name": "starter",
                "price": settings.STARTER_PRICE,
                "daily_limit": settings.STARTER_DAILY_LIMIT,
                "features": ["10,000 requests/day", "5 users", "Priority support", "Webhooks"],
                "payment_link": settings.STRIPE_PAYMENT_LINK_STARTER,
            },
            {
                "name": "pro",
                "price": settings.PRO_PRICE,
                "daily_limit": settings.PRO_DAILY_LIMIT,
                "features": [
                    "100,000 requests/day",
                    "Unlimited users",
                    "24/7 support",
                    "Custom branding",
                    "Analytics",
                ],
                "payment_link": settings.STRIPE_PAYMENT_LINK_PRO,
            },
            {
                "name": "enterprise",
                "price": settings.ENTERPRISE_PRICE,
                "daily_limit": -1,
                "features": [
                    "Unlimited requests",
                    "Unlimited users",
                    "Dedicated support",
                    "SLA",
                    "On-premise option",
                ],
                "payment_link": settings.STRIPE_PAYMENT_LINK_ENTERPRISE,
            },
        ]
    )


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    usage = tier_enforcement.get_usage_info(current_user)
    tier_enforcement._reset_daily_if_needed(current_user)
    await db.commit()
    return UsageResponse(**usage)


@router.post("/webhook", response_model=WebhookResponse)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not settings.STRIPE_WEBHOOK_SECRET:
        return WebhookResponse(status="error", message="Webhook not configured")

    import stripe
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_details", {}).get("email")

        if customer_email:
            stmt = select(User).where(User.email == customer_email)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                metadata = session.get("metadata", {}) or {}
                plan_name = metadata.get("plan")

                if not plan_name:
                    amount = session.get("amount_total", 0)
                    if amount == int(settings.STARTER_PRICE * 100):
                        plan_name = "starter"
                    elif amount == int(settings.PRO_PRICE * 100):
                        plan_name = "pro"
                    elif amount == int(settings.ENTERPRISE_PRICE * 100):
                        plan_name = "enterprise"

                if plan_name:
                    user.plan = plan_name
                    user.plan_expires_at = datetime.now(UTC) + timedelta(days=30)
                    user.stripe_customer_id = session.get("customer")
                    await db.commit()

    return WebhookResponse(status="success", message=f"Handled {event['type']}")


@router.post("/activate")
async def activate_plan(
    plan: str,
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if plan not in ["starter", "pro", "enterprise"]:
        raise HTTPException(status_code=400, detail="Invalid plan")

    current_user.plan = plan
    current_user.plan_expires_at = datetime.now(UTC) + timedelta(days=30)
    await db.commit()

    return {
        "status": "success",
        "plan": plan,
        "expires_at": current_user.plan_expires_at.isoformat(),
        "message": f"Upgraded to {plan} plan. Valid for 30 days.",
    }


@router.post("/cancel")
async def cancel_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.plan = "free"
    current_user.plan_expires_at = None
    await db.commit()

    return {"status": "success", "message": "Downgraded to free plan."}
