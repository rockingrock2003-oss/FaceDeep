from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.models import User


class AuthenticationService:
    async def authenticate(
        self, db: AsyncSession, username: str, password: str
    ) -> User:
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            return None

        return user

    def create_token(self, user_id: str, username: str) -> str:
        return create_access_token(user_id, username)


authentication_service = AuthenticationService()
