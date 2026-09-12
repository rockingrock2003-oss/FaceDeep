from pydantic import BaseModel


class PlanInfoResponse(BaseModel):
    plans: list[dict]


class UsageResponse(BaseModel):
    plan: str
    daily_limit: str | int
    daily_used: int
    daily_remaining: str | int
    plan_expires_at: str | None = None
    plan_price: float
    plans_available: list[dict]


class WebhookResponse(BaseModel):
    status: str
    message: str
