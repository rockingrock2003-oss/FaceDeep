import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(hours=24),
    )
