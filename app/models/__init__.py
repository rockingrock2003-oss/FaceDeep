import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.import_job import ImportJob  # noqa: F401
from app.models.verification import EmailVerification  # noqa: F401


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    api_key_prefix: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # Tracking columns
    entry_in_chroma_db: Mapped[int] = mapped_column(Integer, default=0)
    add_count: Mapped[int] = mapped_column(Integer, default=0)
    delete_count: Mapped[int] = mapped_column(Integer, default=0)
    update_count: Mapped[int] = mapped_column(Integer, default=0)
    number_of_api_use_for_service: Mapped[int] = mapped_column(Integer, default=0)

    # Billing columns
    plan: Mapped[str] = mapped_column(String(20), default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_requests_used: Mapped[int] = mapped_column(Integer, default=0)
    daily_requests_reset_at: Mapped[datetime | None] = mapped_column(  # noqa: E501
        DateTime(timezone=True), nullable=True
    )
    total_revenue_generated: Mapped[float] = mapped_column(Float, default=0.0)
