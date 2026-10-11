from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.sso import SSOCallbackRequest
from app.services.sso import OAUTH_PROVIDERS, sso_service

router = APIRouter(prefix="/sso", tags=["SSO"])


def _redirect_uri(request: Request, provider: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/api/v2/sso/callback/{provider}"


@router.get("/providers")
async def list_providers():
    return {
        "providers": [{"id": key, "name": value["name"]} for key, value in OAUTH_PROVIDERS.items()]
    }


@router.get("/authorize/{provider}")
async def authorize_sso(provider: str, request: Request):
    redirect_uri = _redirect_uri(request, provider)
    state = sso_service.create_state(provider, redirect_uri)
    authorize_url = sso_service.get_authorize_url(provider, redirect_uri, state)

    return {
        "authorize_url": authorize_url,
        "state": state,
        "redirect_uri": redirect_uri,
    }


@router.get("/callback/{provider}")
async def sso_browser_callback(
    provider: str,
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    redirect_uri = _redirect_uri(request, provider)
    sso_service.validate_state(state, provider, redirect_uri)
    return await sso_service.handle_callback(
        db=db,
        provider=provider,
        code=code,
        redirect_uri=redirect_uri,
    )


@router.post("/callback/{provider}")
async def sso_callback(
    provider: str,
    body: SSOCallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    sso_service.validate_state(body.state, provider, body.redirect_uri)
    return await sso_service.handle_callback(
        db=db,
        provider=provider,
        code=body.code,
        redirect_uri=body.redirect_uri,
    )
