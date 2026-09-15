import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    plan: Mapped[str] = mapped_column(String(20), default="free")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    teams = relationship("Team", back_populates="organization", lazy="selectin")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    organization = relationship("Organization", back_populates="teams")
    members = relationship("TeamMember", back_populates="team", lazy="selectin")


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin, editor, viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    team = relationship("Team", back_populates="members")


class TeamApiKey(Base):
    __tablename__ = "team_api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id"), index=True
    )
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    api_key_prefix: Mapped[str] = mapped_column(String(20))
    permissions: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
