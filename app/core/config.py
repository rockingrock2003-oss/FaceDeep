from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://facedeep:facedeep_secret@localhost:5432/facedeep"
    DATABASE_URL_SYNC: str = "postgresql://facedeep:facedeep_secret@localhost:5432/facedeep"

    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    ARCFACE_MODEL_PATH: str = "buffalo_l"
    ARCFACE_DET_SIZE: int = 640
    FACE_RECOGNITION_THRESHOLD: float = 0.4

    LIVENESS_EAR_THRESHOLD: float = 0.21
    LIVENESS_CONSEC_FRAMES: int = 3
    LIVENESS_MIN_SCORE: float = 70.0

    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    POSTGRES_USER: str = "facedeep"
    POSTGRES_PASSWORD: str = "facedeep_secret"
    POSTGRES_DB: str = "facedeep"

    API_V1_PREFIX: str = "/api/v1"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
