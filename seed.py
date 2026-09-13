"""Seed script to create a demo user account.

Usage: python seed.py

Creates:
    Username: demo
    Email: demo@FaceDeep.com
    Password: demo
    API Key: fd_demo_api_key_1234567890
"""

import asyncio
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db import Base
from app.models import User

DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@FaceDeep.com"
DEMO_PASSWORD = "demo"
DEMO_API_KEY = "fd_demo_api_key_1234567890"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def seed():
    engine = create_async_engine(settings.DATABASE_URL)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        stmt = select(User).where(
            (User.username == DEMO_USERNAME) | (User.email == DEMO_EMAIL)
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            print(f"User '{DEMO_USERNAME}' already exists (id={existing.id})")
            print(f"API Key Prefix: {existing.api_key_prefix}")
            await engine.dispose()
            return

        key_hash = hash_api_key(DEMO_API_KEY)
        key_prefix = DEMO_API_KEY[:12] + "..."
        hashed_pw = bcrypt.hash(DEMO_PASSWORD)

        user = User(
            username=DEMO_USERNAME,
            email=DEMO_EMAIL,
            hashed_password=hashed_pw,
            api_key_hash=key_hash,
            api_key_prefix=key_prefix,
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        print("=" * 50)
        print("Demo user created successfully!")
        print("=" * 50)
        print(f"  Username:  {DEMO_USERNAME}")
        print(f"  Email:     {DEMO_EMAIL}")
        print(f"  Password:  {DEMO_PASSWORD}")
        print(f"  API Key:   {DEMO_API_KEY}")
        print(f"  User ID:   {user.id}")
        print("=" * 50)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
