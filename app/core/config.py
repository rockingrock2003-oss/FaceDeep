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

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 300

    ARCFACE_MODEL_PATH: str = "buffalo_l"
    ARCFACE_DET_SIZE: int = 640
    FACE_RECOGNITION_THRESHOLD: float = 0.4

    LIVENESS_MIN_SCORE: float = 70.0
    LIVENESS_EAR_THRESHOLD: float = 0.21
    LIVENESS_CONSEC_FRAMES: int = 3

    LIVENESS_LAYER1_THRESHOLD: float = 70.0
    LIVENESS_LAYER2_THRESHOLD: float = 60.0
    LIVENESS_MAX_IMAGE_AGE_SECONDS: int = 30
    LIVENESS_HMAC_SECRET: str = ""

    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    POSTGRES_USER: str = "facedeep"
    POSTGRES_PASSWORD: str = "facedeep_secret"
    POSTGRES_DB: str = "facedeep"

    API_V1_PREFIX: str = "/api/v1"
    API_V2_PREFIX: str = "/api/v2"

    # Versioning
    API_LATEST_VERSION: str = "v2"
    API_DEPRECATION_SUNSET_V1: str = "2027-03-15"

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

    # SSO / SAML
    SSO_OKTA_CLIENT_ID: str = ""
    SSO_OKTA_CLIENT_SECRET: str = ""
    SSO_AZURE_CLIENT_ID: str = ""
    SSO_AZURE_CLIENT_SECRET: str = ""
    SSO_AZURE_TENANT_ID: str = ""
    SSO_GOOGLE_CLIENT_ID: str = ""
    SSO_GOOGLE_CLIENT_SECRET: str = ""

    # Sentry
    SENTRY_DSN: str = ""

    # Vault / Secrets Management
    VAULT_ADDR: str = "http://127.0.0.1:8200"
    VAULT_TOKEN: str = ""
    VAULT_MOUNT: str = "secret"
    SECRETS_VAULT_ENABLED: bool = False

    # Cloudflare
    CLOUDFLARE_ZONE_ID: str = ""
    CLOUDFLARE_API_TOKEN: str = ""
    CLOUDFLARE_ACCOUNT_ID: str = ""

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
        env_file = (".env.local", ".env.codespace", ".env.production", ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
