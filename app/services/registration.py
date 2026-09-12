from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_password
from app.models import User


class RegistrationService:
    async def check_existing_user(self, db: AsyncSession, username: str, email: str) -> User | None:
        stmt = select(User).where(
            (User.username == username) | (User.email == email)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(
        self, db: AsyncSession, username: str, email: str, password: str
    ) -> tuple[User, str]:
        raw_key, key_hash, key_prefix = generate_api_key()
        hashed_pw = hash_password(password)

        user = User(
            username=username,
            email=email,
            hashed_password=hashed_pw,
            api_key_hash=key_hash,
            api_key_prefix=key_prefix,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

        return user, raw_key


registration_service = RegistrationService()
