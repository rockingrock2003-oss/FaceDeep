import secrets

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


@router.get("/google/authorize")
async def google_authorize():
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return {"url": f"{GOOGLE_AUTH_URL}?{query}", "state": state}


@router.get("/google/callback")
async def google_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
):
    if error:
        return HTMLResponse(
            f"<script>window.close();</script>"
            f"<p>Google sign-in was cancelled: {error}</p>",
            status_code=400,
        )

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    async with httpx.AsyncClient() as client:
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

    if token_resp.status_code != 200:
        raise HTTPException(
            status_code=400, detail="Failed to exchange Google code for token"
        )

    token_data = token_resp.json()
    access_token = token_data.get("access_token")

    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if userinfo_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to get Google user info")

    google_user = userinfo_resp.json()
    google_id = google_user["id"]
    email = google_user.get("email", "")
    name = google_user.get("name", "")
    avatar = google_user.get("picture", "")

    user = await _get_or_create_oauth_user(
        db=db,
        provider="google",
        provider_id=google_id,
        email=email,
        name=name,
        avatar=avatar,
    )

    token = create_access_token(user.id, user.username)

    html = f"""
    <html><body><script>
    window.opener.postMessage({{token: "{token}", username: "{user.username}"}}, "*");
    window.close();
    </script><p>Signed in as {user.username}. You can close this window.</p></body></html>
    """
    return HTMLResponse(html)


@router.get("/apple/authorize")
async def apple_authorize():
    if not settings.APPLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Apple Sign-In not configured",
        )

    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.APPLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI.replace("google", "apple"),
        "response_type": "code id_token",
        "scope": "name email",
        "state": state,
        "response_mode": "form_post",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return {"url": f"{APPLE_AUTH_URL}?{query}", "state": state}


@router.post("/apple/callback")
async def apple_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    code = form.get("code", "")
    id_token_str = form.get("id_token", "")
    user_info_str = form.get("user", "")

    if not code and not id_token_str:
        raise HTTPException(status_code=400, detail="Missing Apple authorization data")

    if id_token_str:
        try:
            payload = jwt.get_unverified_claims(str(id_token_str))
            apple_id = payload.get("sub", "")
            email = payload.get("email", "")
        except JWTError:
            raise HTTPException(status_code=400, detail="Invalid Apple ID token")
    else:
        raise HTTPException(status_code=400, detail="No ID token from Apple")

    name = ""
    if user_info_str:
        import json

        try:
            user_info = json.loads(str(user_info_str))
            name = user_info.get("name", {}).get(
                "firstName", ""
            ) + " " + user_info.get("name", {}).get("lastName", "")
        except (json.JSONDecodeError, AttributeError):
            pass

    user = await _get_or_create_oauth_user(
        db=db,
        provider="apple",
        provider_id=apple_id,
        email=email,
        name=name.strip() or email.split("@")[0],
        avatar="",
    )

    token = create_access_token(user.id, user.username)

    html = f"""
    <html><body><script>
    window.opener.postMessage({{token: "{token}", username: "{user.username}"}}, "*");
    window.close();
    </script><p>Signed in as {user.username}. You can close this window.</p></body></html>
    """
    return HTMLResponse(html)


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

    raw_key, key_hash, key_prefix = generate_api_key()
    username = name.lower().replace(" ", "_") or f"{provider}_{provider_id[:8]}"

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
