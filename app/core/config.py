from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+asyncpg://facedeep:facedeep_secret@localhost:5432/facedeep"
    DATABASE_URL_SYNC: str = "postgresql://facedeep:facedeep_secret@localhost:5432/facedeep"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    ARCFACE_MODEL_PATH: str = "buffalo_l"
    ARCFACE_DET_SIZE: int = 640
    FACE_RECOGNITION_THRESHOLD: float = 0.4

    LIVENESS_MIN_SCORE: float = 70.0

    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    POSTGRES_USER: str = "facedeep"
    POSTGRES_PASSWORD: str = "facedeep_secret"
    POSTGRES_DB: str = "facedeep"

    API_V1_PREFIX: str = "/api/v1"

    # SMTP Email Settings
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "FaceDeep"
    BASE_URL: str = "http://localhost:8000"

    # Security
    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: list[str] = ["*"]

    # OAuth - Google
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # OAuth - Apple
    APPLE_CLIENT_ID: str = ""
    APPLE_TEAM_ID: str = ""
    APPLE_KEY_ID: str = ""
    APPLE_PRIVATE_KEY: str = ""

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Stripe Payment Links (create in Stripe Dashboard → Payment Links)
    STRIPE_PAYMENT_LINK_STARTER: str = ""
    STRIPE_PAYMENT_LINK_PRO: str = ""
    STRIPE_PAYMENT_LINK_ENTERPRISE: str = ""

    # Plan Limits
    FREE_DAILY_LIMIT: int = 100
    STARTER_DAILY_LIMIT: int = 10000
    PRO_DAILY_LIMIT: int = 100000
    ENTERPRISE_DAILY_LIMIT: int = -1  # -1 = unlimited

    # Plan Prices
    STARTER_PRICE: float = 29.0
    PRO_PRICE: float = 99.0
    ENTERPRISE_PRICE: float = 299.0

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
