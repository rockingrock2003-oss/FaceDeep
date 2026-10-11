import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, generate_api_key, hash_password
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["OAuth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"


def _create_oauth_state(provider: str) -> str:
    payload = {
        "provider": provider,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(UTC) + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _validate_oauth_state(state_token: str, provider: str) -> None:
    if not state_token:
        raise HTTPException(status_code=400, detail="Missing OAuth state")
    try:
        payload = jwt.decode(
            state_token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state") from exc

    if payload.get("provider") != provider:
        raise HTTPException(status_code=400, detail="OAuth state provider mismatch")


def _frontend_origin() -> str:
    parsed = urlsplit(settings.FRONTEND_URL)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return settings.FRONTEND_URL.rstrip("/")


def _oauth_result_html(token: str, username: str) -> HTMLResponse:
    payload_json = json.dumps({"token": token, "username": username}).replace("<", "\u003c")
    target_origin = json.dumps(_frontend_origin())
    html = f"""<!doctype html>
<html><body>
<script>
if (window.opener) {{
  window.opener.postMessage({payload_json}, {target_origin});
}}
window.close();
</script>
<p>Sign-in complete. You can close this window.</p>
</body></html>"""
    return HTMLResponse(html)


async def _verify_apple_id_token(id_token: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(APPLE_JWKS_URL)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not verify Apple identity",
        ) from exc

    try:
        header = jwt.get_unverified_header(id_token)
        key = next(
            item for item in response.json().get("keys", []) if item.get("kid") == header.get("kid")
        )
        return jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=settings.APPLE_CLIENT_ID,
            issuer=APPLE_ISSUER,
        )
    except (JWTError, StopIteration, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Apple ID token") from exc


@router.get("/google/authorize")
async def google_authorize():
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    state = _create_oauth_state("google")
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return {"url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}", "state": state}


@router.get("/google/callback")
async def google_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
):
    if error:
        return HTMLResponse(
            "<script>window.close();</script><p>Google sign-in was cancelled.</p>",
            status_code=400,
        )

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    _validate_oauth_state(state, "google")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Google token service",
        ) from exc

    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange Google code for token")

    access_token = token_resp.json().get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Google did not return an access token")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Google user-info service",
        ) from exc

    if userinfo_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to get Google user info")

    google_user = userinfo_resp.json()
    google_id = str(google_user.get("id", ""))
    email = str(google_user.get("email", ""))
    if not google_id or not email:
        raise HTTPException(status_code=400, detail="Google returned incomplete user info")

    user = await _get_or_create_oauth_user(
        db=db,
        provider="google",
        provider_id=google_id,
        email=email,
        name=str(google_user.get("name", "")),
        avatar=str(google_user.get("picture", "")),
    )

    token = create_access_token(user.id, user.username)
    return _oauth_result_html(token, user.username)


@router.get("/apple/authorize")
async def apple_authorize():
    if not settings.APPLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Apple Sign-In not configured",
        )

    state = _create_oauth_state("apple")
    params = {
        "client_id": settings.APPLE_CLIENT_ID,
        "redirect_uri": settings.APPLE_REDIRECT_URI,
        "response_type": "code id_token",
        "scope": "name email",
        "state": state,
        "response_mode": "form_post",
    }
    return {"url": f"{APPLE_AUTH_URL}?{urlencode(params)}", "state": state}


@router.post("/apple/callback")
async def apple_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    if form.get("error"):
        return HTMLResponse(
            "<script>window.close();</script><p>Apple sign-in was cancelled.</p>",
            status_code=400,
        )

    state_token = str(form.get("state", ""))
    _validate_oauth_state(state_token, "apple")

    id_token_str = str(form.get("id_token", ""))
    if not id_token_str:
        raise HTTPException(status_code=400, detail="No ID token from Apple")

    payload = await _verify_apple_id_token(id_token_str)
    apple_id = str(payload.get("sub", ""))
    email = str(payload.get("email", ""))
    if not apple_id:
        raise HTTPException(status_code=400, detail="Apple returned incomplete user info")

    name = ""
    user_info_str = form.get("user")
    if user_info_str:
        try:
            user_info = json.loads(str(user_info_str))
            first = user_info.get("name", {}).get("firstName", "")
            last = user_info.get("name", {}).get("lastName", "")
            name = f"{first} {last}".strip()
        except (json.JSONDecodeError, AttributeError):
            pass

    user = await _get_or_create_oauth_user(
        db=db,
        provider="apple",
        provider_id=apple_id,
        email=email,
        name=name or (email.split("@")[0] if email else ""),
        avatar="",
    )

    token = create_access_token(user.id, user.username)
    return _oauth_result_html(token, user.username)


def _safe_username(name: str, provider: str, provider_id: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "_", name.lower()).strip("._-")
    return normalized[:50] or f"{provider}_{provider_id[:8]}"


async def _get_or_create_oauth_user(
    db: AsyncSession,
    provider: str,
    provider_id: str,
    email: str,
    name: str,
    avatar: str,
) -> User:
    stmt = select(User).where(
        User.oauth_provider == provider,
        User.oauth_id == provider_id,
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        if avatar and user.avatar_url != avatar:
            user.avatar_url = avatar
            await db.commit()
        return user

    if not email:
        raise HTTPException(
            status_code=400,
            detail=f"{provider.title()} did not provide an email address",
        )

    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        existing_user.oauth_provider = provider
        existing_user.oauth_id = provider_id
        if avatar:
            existing_user.avatar_url = avatar
        existing_user.is_verified = True
        await db.commit()
        await db.refresh(existing_user)
        return existing_user

    _, key_hash, key_prefix = generate_api_key()
    username = _safe_username(name, provider, provider_id)

    base_username = username
    counter = 1
    while True:
        check = select(User).where(User.username == username)
        check_result = await db.execute(check)
        if not check_result.scalar_one_or_none():
            break
        username = f"{base_username}_{counter}"
        counter += 1

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        api_key_hash=key_hash,
        api_key_prefix=key_prefix,
        oauth_provider=provider,
        oauth_id=provider_id,
        avatar_url=avatar or None,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
