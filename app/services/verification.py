import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.verification import EmailVerification
from app.services.email_service import email_service


class VerificationService:
    def _generate_token(self) -> str:
        return secrets.token_urlsafe(48)

    async def create_verification(self, db: AsyncSession, user: User) -> str:
        token = self._generate_token()

        verification = EmailVerification(
            user_id=user.id,
            token=token,
        )
        db.add(verification)
        await db.flush()

        return token

    async def send_verification_email(self, user: User, token: str):
        email_service.send_verification_email(
            to_email=user.email,
            username=user.username,
            token=token,
        )

    async def verify_token(self, db: AsyncSession, token: str) -> bool:
        stmt = select(EmailVerification).where(
            EmailVerification.token == token,
            EmailVerification.is_used == False,
        )
        result = await db.execute(stmt)
        verification = result.scalar_one_or_none()

        if not verification:
            return False

        if verification.expires_at < datetime.now(timezone.utc):
            return False

        verification.is_used = True

        user_stmt = select(User).where(User.id == verification.user_id)
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()

        if not user:
            return False

        user.is_verified = True
        await db.flush()

        return True

    async def resend_verification(self, db: AsyncSession, user: User) -> str | None:
        if user.is_verified:
            return None

        stmt = (
            select(EmailVerification)
            .where(
                EmailVerification.user_id == user.id,
                EmailVerification.is_used == False,
            )
            .order_by(EmailVerification.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.is_used = True

        token = await self.create_verification(db, user)
        await self.send_verification_email(user, token)

        return token


verification_service = VerificationService()
