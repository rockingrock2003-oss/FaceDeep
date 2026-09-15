from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.models.audit_log import AuditLog
from app.models.organization import Organization, Team, TeamApiKey, TeamMember
from app.schemas.webhook import WebhookSubscriptionResponse
from app.services.organization import organization_service
from app.services.security_service import security_service

router = APIRouter(prefix="/organizations", tags=["Multi-tenancy"])


class CreateOrgRequest(BaseModel):
    name: str
    slug: str


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "viewer"


class CreateTeamKeyRequest(BaseModel):
    team_id: str
    permissions: list[str] | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: CreateOrgRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org = await organization_service.create_organization(db, body.name, body.slug, current_user.id)
    await security_service.log_audit(
        user_id=current_user.id,
        action="organization.created",
        resource_type="organization",
        resource_id=org.id,
        details=f"Name: {body.name}, Slug: {body.slug}",
    )
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "owner_id": org.owner_id,
        "created_at": org.created_at.isoformat(),
    }


@router.get("")
async def list_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    orgs = await organization_service.get_user_organizations(db, current_user.id)
    return {
        "status": "success",
        "count": len(orgs),
        "organizations": [
            {
                "id": o.id,
                "name": o.name,
                "slug": o.slug,
                "owner_id": o.owner_id,
                "plan": o.plan,
                "created_at": o.created_at.isoformat(),
            }
            for o in orgs
        ],
    }


@router.get("/{org_id}")
async def get_organization(
    org_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Organization).where(Organization.id == org_id)
    result = await db.execute(stmt)
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    role = await organization_service.check_team_permission(db, current_user.id, None)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this organization")

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "owner_id": org.owner_id,
        "plan": org.plan,
        "created_at": org.created_at.isoformat(),
    }


@router.post("/{org_id}/members")
async def add_member(
    org_id: str,
    body: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Team).where(Team.organization_id == org_id)
    result = await db.execute(stmt)
    teams = result.scalars().all()
    if not teams:
        raise HTTPException(status_code=404, detail="No teams found in organization")

    member = await organization_service.add_member(db, teams[0].id, body.user_id, body.role)

    await security_service.log_audit(
        user_id=current_user.id,
        action="member.added",
        resource_type="team_member",
        resource_id=member.id,
        details=f"User: {body.user_id}, Role: {body.role}",
    )

    return {
        "status": "success",
        "member_id": member.id,
        "team_id": member.team_id,
        "user_id": member.user_id,
        "role": member.role,
    }


@router.post("/{org_id}/api-keys")
async def create_team_api_key(
    org_id: str,
    body: CreateTeamKeyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await organization_service.create_team_api_key(
        db, body.team_id, org_id, body.permissions
    )

    await security_service.log_audit(
        user_id=current_user.id,
        action="team_api_key.created",
        resource_type="team_api_key",
        resource_id=org_id,
        details=f"Team: {body.team_id}",
    )

    return result


@router.get("/{org_id}/audit-log")
async def get_audit_log(
    org_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AuditLog)
        .where(AuditLog.user_id == current_user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return {
        "status": "success",
        "count": len(logs),
        "logs": [
            {
                "id": l.id,
                "action": l.action,
                "resource_type": l.resource_type,
                "resource_id": l.resource_id,
                "details": l.details,
                "ip_address": l.ip_address,
                "created_at": l.created_at.isoformat(),
            }
            for l in logs
        ],
    }
