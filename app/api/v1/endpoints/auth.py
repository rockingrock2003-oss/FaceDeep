from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key
from app.core.security import get_current_user as _get_user
from app.db import get_db
from app.models import User
from app.schemas.auth import (
    ApiKeyResponse,
    ChangePasswordRequest,
    ResendVerificationResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    VerifyEmailResponse,
)
from app.services.authentication import authentication_service
from app.services.registration import registration_service
from app.services.verification import verification_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register")
async def register_user(body: UserRegister, db: AsyncSession = Depends(get_db)):
    existing = await registration_service.check_existing_user(
        db, body.username, body.email
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    user, _raw_key = await registration_service.create_user(
        db, body.username, body.email, body.password
    )

    token = await verification_service.create_verification(db, user)
    try:
        await verification_service.send_verification_email(user, token)
    except Exception:
        pass

    access_token = authentication_service.create_token(user.id, user.username)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
    }


@router.get("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    success = await verification_service.verify_token(db, token)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    return VerifyEmailResponse(
        status="success",
        message="Email verified successfully. You can now login.",
    )


@router.post("/resend-verification", response_model=ResendVerificationResponse)
async def resend_verification(
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    user = await authentication_service.authenticate(db, body.username, body.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified",
        )

    await verification_service.resend_verification(db, user)

    return ResendVerificationResponse(
        status="success",
        message="Verification email sent. Check your inbox.",
    )


@router.post("/login")
async def login_user(body: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await authentication_service.authenticate(db, body.username, body.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your email first.",
        )

    token = authentication_service.create_token(user.id, user.username)

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
    current_user: User = Depends(_get_user),
):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        api_key=None,
        api_key_prefix=current_user.api_key_prefix,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at.isoformat(),
        plan=current_user.plan,
        plan_expires_at=(
            current_user.plan_expires_at.isoformat()
            if current_user.plan_expires_at
            else None
        ),
        daily_requests_used=current_user.daily_requests_used,
        entry_in_chroma_db=current_user.entry_in_chroma_db,
        add_count=current_user.add_count,
        delete_count=current_user.delete_count,
        update_count=current_user.update_count,
        number_of_api_use_for_service=current_user.number_of_api_use_for_service,
    )


@router.get("/api-key", response_model=ApiKeyResponse)
async def get_api_key(
    current_user: User = Depends(_get_user),
):
    return ApiKeyResponse(
        api_key_prefix=current_user.api_key_prefix,
    )


@router.post("/api-key/regenerate", response_model=ApiKeyResponse)
async def regenerate_api_key(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_user),
):
    raw_key, key_hash, key_prefix = generate_api_key()
    current_user.api_key_hash = key_hash
    current_user.api_key_prefix = key_prefix
    await db.commit()

    return ApiKeyResponse(
        api_key=raw_key,
        api_key_prefix=key_prefix,
    )


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_user),
):
    from app.core.security import hash_password, verify_password

    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if len(body.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters",
        )

    current_user.hashed_password = hash_password(body.new_password)
    await db.commit()

    return {"status": "success", "message": "Password changed successfully"}
