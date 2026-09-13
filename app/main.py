import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.db import Base, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("facedeep")

executor = ThreadPoolExecutor(max_workers=2)


def _preload_models():
    try:
        from app.services.face_recognition import get_face_service
        get_face_service()
        logger.info("ArcFace model loaded")
    except Exception as e:
        logger.warning(f"Failed to preload ArcFace: {e}")

    try:
        import mediapipe as mp
        if hasattr(mp, 'solutions'):
            from app.services.liveness import LivenessDetector
            d = LivenessDetector()
            d._get_face_mesh()
            logger.info("MediaPipe FaceMesh loaded")
        else:
            logger.info("MediaPipe installed but liveness module unavailable (Python 3.14?)")
    except Exception as e:
        logger.info(f"MediaPipe not preloaded: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    executor.submit(_preload_models)

    yield

    await engine.dispose()
    executor.shutdown(wait=False)


app = FastAPI(
    title="FaceDeep - Facial Recognition API",
    description="Facial Recognition API with ArcFace, ChromaDB, and Liveness Detection",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "FaceDeep API"}
