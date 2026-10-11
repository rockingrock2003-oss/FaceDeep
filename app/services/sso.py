import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import User

logger = logging.getLogger("facedeep.sso")

OAUTH_PROVIDERS = {
    "okta": {
        "name": "Okta",
        "scopes": ["openid", "email", "profile"],
    },
    "azure": {
        "name": "Azure AD",
        "scopes": ["openid", "email", "profile"],
    },
    "google_workspace": {
        "name": "Google Workspace",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
}


class SSOService:
    def get_provider_config(self, provider: str) -> dict:
        if provider not in OAUTH_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unknown SSO provider: {provider}. Available: {list(OAUTH_PROVIDERS.keys())}"
                ),
            )

        config = dict(OAUTH_PROVIDERS[provider])
        if provider == "okta":
            issuer = settings.SSO_OKTA_ISSUER.rstrip("/")
            if not issuer:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="Okta SSO is not configured",
                )
            config.update(
                client_id=settings.SSO_OKTA_CLIENT_ID,
                client_secret=settings.SSO_OKTA_CLIENT_SECRET,
                authorize_url=f"{issuer}/v1/authorize",
                token_url=f"{issuer}/v1/token",
                userinfo_url=f"{issuer}/v1/userinfo",
            )
        elif provider == "azure":
            tenant = settings.SSO_AZURE_TENANT_ID
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="Azure SSO is not configured",
                )
            base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
            config.update(
                client_id=settings.SSO_AZURE_CLIENT_ID,
                client_secret=settings.SSO_AZURE_CLIENT_SECRET,
                authorize_url=f"{base}/authorize",
                token_url=f"{base}/token",
                userinfo_url="https://graph.microsoft.com/oidc/userinfo",
            )
        else:
            config.update(
                client_id=settings.SSO_GOOGLE_CLIENT_ID,
                client_secret=settings.SSO_GOOGLE_CLIENT_SECRET,
            )

        if not config.get("client_id") or not config.get("client_secret"):
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"{config['name']} SSO is not configured",
            )
        return config

    def create_state(self, provider: str, redirect_uri: str) -> str:
        payload = {
            "provider": provider,
            "redirect_uri": redirect_uri,
            "nonce": secrets.token_urlsafe(16),
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    def validate_state(self, state_token: str, provider: str, redirect_uri: str) -> None:
        try:
            payload = jwt.decode(
                state_token,
                settings.SECRET_KEY,
                algorithms=["HS256"],
            )
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired SSO state",
            ) from exc

        if payload.get("provider") != provider or payload.get("redirect_uri") != redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SSO state does not match this callback",
            )

    def get_authorize_url(self, provider: str, redirect_uri: str, state: str) -> str:
        config = self.get_provider_config(provider)
        params = {
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(config["scopes"]),
            "state": state,
        }
        return f"{config['authorize_url']}?{urlencode(params)}"

    async def handle_callback(
        self,
        db: AsyncSession,
        provider: str,
        code: str,
        redirect_uri: str,
    ) -> dict:
        config = self.get_provider_config(provider)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                token_resp = await client.post(
                    config["token_url"],
                    data={
                        "code": code,
                        "client_id": config["client_id"],
                        "client_secret": config["client_secret"],
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
        except httpx.HTTPError as exc:
            logger.warning("%s token exchange failed: %s", provider, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not reach {config['name']} token service",
            ) from exc

        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange {provider} code for token",
            )

        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{config['name']} did not return an access token",
            )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                userinfo_resp = await client.get(
                    config["userinfo_url"],
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            logger.warning("%s user-info request failed: %s", provider, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not reach {config['name']} user-info service",
            ) from exc

        if userinfo_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get user info from {provider}",
            )

        userinfo = userinfo_resp.json()
        email = userinfo.get("email", "")
        name = userinfo.get("name", "")
        provider_id = userinfo.get("sub", userinfo.get("id", ""))

        if not email or not provider_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incomplete user info returned from {provider}",
            )

        user = await self._get_or_create_sso_user(
            db=db,
            provider=provider,
            provider_id=provider_id,
            email=email,
            name=name,
        )

        from app.core.security import create_access_token

        token = create_access_token(user.id, user.username)
        return {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user.id,
            "username": user.username,
            "provider": provider,
        }

    async def _get_or_create_sso_user(
        self,
        db: AsyncSession,
        provider: str,
        provider_id: str,
        email: str,
        name: str,
    ) -> User:
        stmt = select(User).where(
            User.oauth_provider == provider,
            User.oauth_id == provider_id,
        )
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user

        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.oauth_provider = provider
            existing.oauth_id = provider_id
            existing.is_verified = True
            await db.commit()
            await db.refresh(existing)
            return existing

        from app.core.security import generate_api_key, hash_password

        _, key_hash, key_prefix = generate_api_key()
        username = name.lower().strip().replace(" ", "_")
        username = username or f"sso_{provider}_{provider_id[:8]}"

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
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


sso_service = SSOService()
