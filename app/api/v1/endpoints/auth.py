from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import get_current_user as _get_user
from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.db import get_db
from app.models import User
from app.schemas.auth import UserLogin, UserRegister, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(body: UserRegister, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    raw_key, key_hash, key_prefix = generate_api_key()
    hashed_pw = hash_password(body.password)

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hashed_pw,
        api_key_hash=key_hash,
        api_key_prefix=key_prefix,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        api_key=raw_key,
        api_key_prefix=user.api_key_prefix,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
    )


@router.post("/login")
async def login_user(body: UserLogin, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.username == body.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    token = create_access_token(user.id, user.username)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "api_key_prefix": user.api_key_prefix,
    }


@router.get("/me", response_model=UserResponse)
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: None)):


    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        api_key=None,
        api_key_prefix=current_user.api_key_prefix,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
    )
