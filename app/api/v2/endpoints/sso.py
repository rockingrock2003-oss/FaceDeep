import secrets
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.sso import SSOCallbackRequest
from app.services.sso import sso_service

router = APIRouter(prefix="/sso", tags=["SSO"])


@router.get("/providers")
async def list_providers():
    from app.services.sso import OAUTH_PROVIDERS

    return {
        "providers": [
            {"id": k, "name": v["name"]}
            for k, v in OAUTH_PROVIDERS.items()
        ]
    }


@router.get("/authorize/{provider}")
async def authorize_sso(provider: str, request: Request):
    state = secrets.token_urlsafe(32)
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/v2/sso/callback/{provider}"
    authorize_url = sso_service.get_authorize_url(provider, redirect_uri, state)

    return {
        "authorize_url": authorize_url,
        "state": state,
        "redirect_uri": redirect_uri,
    }


@router.post("/callback/{provider}")
async def sso_callback(
    provider: str,
    body: SSOCallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await sso_service.handle_callback(
        db=db,
        provider=provider,
        code=body.code,
        redirect_uri=body.redirect_uri,
    )
    return result
