import json
import logging
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_api_key
from app.models import User
from app.models.organization import Organization, Team, TeamApiKey, TeamMember

logger = logging.getLogger("facedeep.organization")

VALID_ROLES = {"admin", "editor", "viewer"}


class OrganizationService:
    async def create_organization(
        self, db: AsyncSession, name: str, slug: str, owner_id: str
    ) -> Organization:
        existing = await db.execute(select(Organization).where(Organization.slug == slug))
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
        stmt = select(TeamMember).where(TeamMember.user_id == user_id)
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

    async def add_member(
        self,
        db: AsyncSession,
        team_id: str,
        user_id: str,
        role: str = "viewer",
    ) -> TeamMember:
        if role not in VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role: {role}. Must be one of: {sorted(VALID_ROLES)}",
            )

        user_result = await db.execute(select(User.id).where(User.id == user_id))
        if user_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="User not found")

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
        self,
        db: AsyncSession,
        team_id: str,
        organization_id: str,
        permissions: list[str] | None = None,
    ) -> dict:
        raw_key = f"fda_{secrets.token_urlsafe(32)}"
        key_hash = hash_api_key(raw_key)
        key_prefix = raw_key[:12] + "..."

        resolved_permissions = (
            permissions if permissions is not None else ["face:read", "face:write"]
        )
        invalid_permissions = set(resolved_permissions) - {"face:read", "face:write", "*"}
        if invalid_permissions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid permissions: {sorted(invalid_permissions)}",
            )

        key = TeamApiKey(
            team_id=team_id,
            organization_id=organization_id,
            api_key_hash=key_hash,
            api_key_prefix=key_prefix,
            permissions=json.dumps(resolved_permissions),
        )
        db.add(key)
        await db.commit()

        return {
            "api_key": raw_key,
            "api_key_prefix": key_prefix,
            "team_id": team_id,
            "permissions": resolved_permissions,
        }

    async def check_team_permission(
        self,
        db: AsyncSession,
        user_id: str,
        team_id: str,
    ) -> str | None:
        stmt = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
        result = await db.execute(stmt)
        member = result.scalar_one_or_none()
        return member.role if member else None

    async def get_organization_role(
        self,
        db: AsyncSession,
        user_id: str,
        organization_id: str,
    ) -> str | None:
        stmt = (
            select(TeamMember.role)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.organization_id == organization_id,
                TeamMember.user_id == user_id,
            )
        )
        result = await db.execute(stmt)
        roles = result.scalars().all()
        if not roles:
            return None

        rank = {"viewer": 1, "editor": 2, "admin": 3}
        return max(roles, key=lambda role: rank.get(role, 0))

    async def get_team(
        self,
        db: AsyncSession,
        team_id: str,
        organization_id: str,
    ) -> Team | None:
        stmt = select(Team).where(
            Team.id == team_id,
            Team.organization_id == organization_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


organization_service = OrganizationService()
