from pydantic import BaseModel, Field, HttpUrl


class WebhookSubscriptionCreate(BaseModel):
    url: str = Field(..., description="HTTPS endpoint URL for webhook delivery")
    events: list[str] = Field(..., description="Event types to subscribe to")


class WebhookSubscriptionResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    is_active: bool
    secret: str | None = None
    created_at: str


class WebhookSubscriptionUpdate(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None


class WebhookDeliveryResponse(BaseModel):
    id: str
    event: str
    status: str
    status_code: int | None = None
    attempts: int
    max_attempts: int
    created_at: str
    delivered_at: str | None = None


class WebhookTestResponse(BaseModel):
    status: str
    message: str
    status_code: int | None = None
