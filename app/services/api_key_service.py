import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_api_key
from app.models import User


class ApiKeyService:
    async def validate_api_key(self, db: AsyncSession, api_key: str) -> User | None:
        key_hash = hash_api_key(api_key)

        stmt = select(User).where(User.api_key_hash == key_hash)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            time.sleep(0.05)
            return None

        return user

    async def increment_api_usage(self, db: AsyncSession, user: User):
        user.number_of_api_use_for_service += 1
        await db.commit()


api_key_service = ApiKeyService()
