import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

        raw_key, key_hash, key_prefix = generate_api_key()

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

        logger.info("=" * 60)
        logger.info("TEST USER CREATED:")
        logger.info(f"  Username : {TEST_USER['username']}")
        logger.info(f"  Password : {TEST_USER['password']}")
        logger.info(f"  Email    : {TEST_USER['email']}")
        logger.info(f"  Plan     : enterprise")
        logger.info(f"  API Key  : {raw_key}")
        logger.info(f"  User ID  : {user.id}")
        logger.info("=" * 60)

        print("\n" + "=" * 60)
        print("TEST USER CREATED:")
        print(f"  Username : {TEST_USER['username']}")
        print(f"  Password : {TEST_USER['password']}")
        print(f"  Email    : {TEST_USER['email']}")
        print(f"  Plan     : enterprise")
        print(f"  API Key  : {raw_key}")
        print(f"  User ID  : {user.id}")
        print("=" * 60 + "\n")

        return user
