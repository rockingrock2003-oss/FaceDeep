import hashlib
import logging
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import User

logger = logging.getLogger("facedeep.sso")

OAUTH_PROVIDERS = {
    "okta": {
        "name": "Okta",
        "authorize_url": "https://your-domain.okta.com/oauth2/v1/authorize",
        "token_url": "https://your-domain.okta.com/oauth2/v1/token",
        "userinfo_url": "https://your-domain.okta.com/oauth2/v1/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
    "azure": {
        "name": "Azure AD",
        "authorize_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
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
                detail=f"Unknown SSO provider: {provider}. Available: {list(OAUTH_PROVIDERS.keys())}",
            )
        return OAUTH_PROVIDERS[provider]

    def get_authorize_url(self, provider: str, redirect_uri: str, state: str) -> str:
        config = self.get_provider_config(provider)
        params = {
            "client_id": f"SSO_{provider.upper()}_CLIENT_ID",
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(config["scopes"]),
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{config['authorize_url']}?{query}"

    async def handle_callback(
        self,
        db: AsyncSession,
        provider: str,
        code: str,
        redirect_uri: str,
    ) -> dict:
        import httpx

        config = self.get_provider_config(provider)

        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                config["token_url"],
                data={
                    "code": code,
                    "client_id": f"SSO_{provider.upper()}_CLIENT_ID",
                    "client_secret": f"SSO_{provider.upper()}_CLIENT_SECRET",
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange {provider} code for token",
            )

        access_token = token_resp.json().get("access_token")

        async with httpx.AsyncClient() as client:
            userinfo_resp = await client.get(
                config["userinfo_url"],
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if userinfo_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get user info from {provider}",
            )

        userinfo = userinfo_resp.json()
        email = userinfo.get("email", "")
        name = userinfo.get("name", "")
        provider_id = userinfo.get("sub", userinfo.get("id", ""))

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No email returned from {provider}",
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

        raw_key, key_hash, key_prefix = generate_api_key()
        username = name.lower().replace(" ", "_") or f"sso_{provider}_{provider_id[:8]}"

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
