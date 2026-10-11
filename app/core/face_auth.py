import asyncio
import json
from typing import NamedTuple

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, hash_api_key
from app.db import get_db
from app.models import User
from app.models.organization import Organization, TeamApiKey

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


class FaceAuthContext(NamedTuple):
    user: User
    db: AsyncSession
    namespace: str


def _required_team_permission(request: Request) -> str:
    if request.method == "GET":
        return "face:read"
    if request.url.path.endswith(("/recognize", "/ismatch")):
        return "face:read"
    return "face:write"


async def _active_user_by_id(db: AsyncSession, user_id: str | None) -> User | None:
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    return user if user and user.is_active and user.is_verified else None


async def resolve_face_auth(
    request: Request,
    api_key: str | None = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> FaceAuthContext:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        payload = decode_access_token(auth_header[7:])
        user = await _active_user_by_id(db, payload.get("sub"))
        if user:
            return FaceAuthContext(user, db, user.id)

    if api_key:
        key_hash = hash_api_key(api_key)

        result = await db.execute(select(User).where(User.api_key_hash == key_hash))
        user = result.scalar_one_or_none()
        if user and user.is_active and not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please verify your email first.",
            )
        if user and user.is_active:
            return FaceAuthContext(user, db, user.id)

        result = await db.execute(
            select(TeamApiKey).where(
                TeamApiKey.api_key_hash == key_hash,
                TeamApiKey.is_active.is_(True),
            )
        )
        team_key = result.scalar_one_or_none()
        if team_key:
            try:
                permissions = set(json.loads(team_key.permissions or "[]"))
            except (TypeError, json.JSONDecodeError):
                permissions = set()

            required = _required_team_permission(request)
            if required not in permissions and "*" not in permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Team API key requires '{required}' permission",
                )

            result = await db.execute(
                select(Organization).where(Organization.id == team_key.organization_id)
            )
            organization = result.scalar_one_or_none()
            if organization:
                owner = await _active_user_by_id(db, organization.owner_id)
                if owner:
                    return FaceAuthContext(
                        owner,
                        db,
                        f"org_{organization.id}",
                    )

    await asyncio.sleep(0.05)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
