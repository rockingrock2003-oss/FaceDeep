from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.billing import PlanInfoResponse, UsageResponse
from app.services.metering import metering_service
from app.services.tier_service import tier_enforcement

router = APIRouter(prefix="/billing", tags=["Billing & Metering"])


class ActivatePlanRequest(BaseModel):
    plan: str
    session_id: str


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


@router.get("/realtime-usage")
async def get_realtime_usage(
    current_user: User = Depends(get_current_user),
):
    return await metering_service.get_realtime_usage(current_user.id)


@router.get("/monthly-cost")
async def get_monthly_cost(
    current_user: User = Depends(get_current_user),
):
    cost = await metering_service.get_monthly_cost(current_user.id)
    return {
        "cost_this_month": round(cost, 4),
        "currency": "USD",
    }


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    from datetime import UTC, datetime, timedelta

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not settings.STRIPE_WEBHOOK_SECRET:
        return {"status": "error", "message": "Webhook not configured"}

    import stripe

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        if session.get("payment_status") != "paid":
            return {"status": "ignored", "message": "Checkout session is not paid"}

        customer_email = (session.get("customer_details") or {}).get("email")
        if customer_email:
            stmt = select(User).where(User.email == customer_email)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                metadata = session.get("metadata", {}) or {}
                plan_name = metadata.get("plan")
                valid_plans = {"starter", "pro", "enterprise"}

                if plan_name not in valid_plans:
                    amount = session.get("amount_total", 0)
                    amount_to_plan = {
                        int(settings.STARTER_PRICE * 100): "starter",
                        int(settings.PRO_PRICE * 100): "pro",
                        int(settings.ENTERPRISE_PRICE * 100): "enterprise",
                    }
                    plan_name = amount_to_plan.get(amount)

                if plan_name in valid_plans:
                    user.plan = plan_name
                    user.plan_expires_at = datetime.now(UTC) + timedelta(days=30)
                    user.stripe_customer_id = session.get("customer")
                    await db.commit()

    return {"status": "success", "message": f"Handled {event['type']}"}


@router.post("/activate")
async def activate_plan(
    body: ActivatePlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import UTC, datetime, timedelta

    import stripe

    if body.plan not in {"starter", "pro", "enterprise"}:
        raise HTTPException(status_code=400, detail="Invalid plan")
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured",
        )

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.retrieve(body.session_id)
    except stripe.StripeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe checkout session",
        ) from exc

    if session.get("payment_status") != "paid":
        raise HTTPException(status_code=400, detail="Checkout session is not paid")

    customer_email = (session.get("customer_details") or {}).get("email")
    if customer_email and customer_email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Checkout session belongs to a different customer",
        )

    expected_amounts = {
        "starter": int(settings.STARTER_PRICE * 100),
        "pro": int(settings.PRO_PRICE * 100),
        "enterprise": int(settings.ENTERPRISE_PRICE * 100),
    }
    metadata_plan = (session.get("metadata") or {}).get("plan")
    amount_total = session.get("amount_total")
    if metadata_plan and metadata_plan != body.plan:
        raise HTTPException(status_code=400, detail="Checkout session plan does not match")
    if not metadata_plan and amount_total != expected_amounts[body.plan]:
        raise HTTPException(status_code=400, detail="Checkout session amount does not match plan")

    current_user.plan = body.plan
    current_user.plan_expires_at = datetime.now(UTC) + timedelta(days=30)
    current_user.stripe_customer_id = session.get("customer")
    await db.commit()

    return {
        "status": "success",
        "plan": body.plan,
        "expires_at": current_user.plan_expires_at.isoformat(),
        "message": f"Upgraded to {body.plan} plan. Valid for 30 days.",
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
