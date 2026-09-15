from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    endpoint: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(10))
    status_code: Mapped[int] = mapped_column(Integer)
    response_time_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
