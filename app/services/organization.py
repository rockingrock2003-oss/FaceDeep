import json
import logging
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_api_key
from app.models.organization import Organization, Team, TeamApiKey, TeamMember

logger = logging.getLogger("facedeep.organization")

VALID_ROLES = {"admin", "editor", "viewer"}


class OrganizationService:
    async def create_organization(self, db: AsyncSession, name: str, slug: str, owner_id: str) -> Organization:
        existing = await db.execute(
            select(Organization).where(Organization.slug == slug)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Organization slug '{slug}' already exists",
            )

        org = Organization(name=name, slug=slug, owner_id=owner_id)
        db.add(org)
        await db.flush()

        team = Team(name="Default", organization_id=org.id)
        db.add(team)
        await db.flush()

        member = TeamMember(team_id=team.id, user_id=owner_id, role="admin")
        db.add(member)
        await db.commit()
        await db.refresh(org)

        return org

    async def get_user_organizations(self, db: AsyncSession, user_id: str) -> list[Organization]:
        stmt = (
            select(TeamMember)
            .where(TeamMember.user_id == user_id)
        )
        result = await db.execute(stmt)
        memberships = result.scalars().all()

        if not memberships:
            return []

        team_ids = [m.team_id for m in memberships]
        stmt = select(Team).where(Team.id.in_(team_ids))
        result = await db.execute(stmt)
        teams = result.scalars().all()

        org_ids = list({t.organization_id for t in teams})
        if not org_ids:
            return []

        stmt = select(Organization).where(Organization.id.in_(org_ids))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def add_member(self, db: AsyncSession, team_id: str, user_id: str, role: str = "viewer") -> TeamMember:
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}. Must be one of: {VALID_ROLES}")

        existing = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="User already a member of this team")

        member = TeamMember(team_id=team_id, user_id=user_id, role=role)
        db.add(member)
        await db.commit()
        return member

    async def create_team_api_key(
        self, db: AsyncSession, team_id: str, organization_id: str, permissions: list[str] | None = None
    ) -> dict:
        raw_key = f"fda_{secrets.token_urlsafe(32)}"
        key_hash = hash_api_key(raw_key)
        key_prefix = raw_key[:12] + "..."

        key = TeamApiKey(
            team_id=team_id,
            organization_id=organization_id,
            api_key_hash=key_hash,
            api_key_prefix=key_prefix,
            permissions=json.dumps(permissions or []),
        )
        db.add(key)
        await db.commit()

        return {
            "api_key": raw_key,
            "api_key_prefix": key_prefix,
            "team_id": team_id,
            "permissions": permissions or [],
        }

    async def check_team_permission(self, db: AsyncSession, user_id: str, team_id: str) -> str | None:
        stmt = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
        result = await db.execute(stmt)
        member = result.scalar_one_or_none()
        return member.role if member else None


organization_service = OrganizationService()
