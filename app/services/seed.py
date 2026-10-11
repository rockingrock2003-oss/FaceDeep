import logging

from sqlalchemy import select

from app.core.security import generate_api_key, hash_password
from app.db import AsyncSessionLocal
from app.models import User

logger = logging.getLogger("facedeep.seed")

TEST_USER = {
    "username": "admin",
    "email": "admin@facedeep.com",
    "password": "admin123",
}


async def seed_test_user():
    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.username == TEST_USER["username"])
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Test user '{TEST_USER['username']}' already exists (id={existing.id})")
            return existing

        _raw_key, key_hash, key_prefix = generate_api_key()

        user = User(
            username=TEST_USER["username"],
            email=TEST_USER["email"],
            hashed_password=hash_password(TEST_USER["password"]),
            api_key_hash=key_hash,
            api_key_prefix=key_prefix,
            is_active=True,
            is_verified=True,
            plan="enterprise",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(
            "Test user created (username=%s, email=%s, user_id=%s). "
            "Use the login flow and API-key regeneration endpoint to obtain credentials.",
            TEST_USER["username"],
            TEST_USER["email"],
            user.id,
        )

        return user
