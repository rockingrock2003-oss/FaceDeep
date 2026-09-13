from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    api_key: str | None = None
    api_key_prefix: str
    is_active: bool
    is_verified: bool = False
    created_at: str
    plan: str = "free"
    plan_expires_at: str | None = None
    daily_requests_used: int = 0
    entry_in_chroma_db: int = 0
    add_count: int = 0
    delete_count: int = 0
    update_count: int = 0
    number_of_api_use_for_service: int = 0

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


class VerifyEmailResponse(BaseModel):
    status: str
    message: str


class ResendVerificationResponse(BaseModel):
    status: str
    message: str


class ApiKeyResponse(BaseModel):
    api_key: str | None = None
    api_key_prefix: str
