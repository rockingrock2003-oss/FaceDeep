import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router as v1_router
from app.api.v2.router import api_router as v2_router
from app.core.config import settings
from app.core.metrics import metrics
from app.core.request_logger import RequestLoggingMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.structured_logging import setup_logging
from app.core.versioning import APIVersioningMiddleware
from app.db import Base, engine

setup_logging(environment=settings.ENVIRONMENT)

from app.core.sentry import init_sentry

init_sentry()
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.cache import cache
    from app.services.worker import worker_pool

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    executor.submit(_preload_models)
    await cache.connect()
    await worker_pool.start()

    from app.services.seed import seed_test_user

    await seed_test_user()

    yield

    await worker_pool.stop()
    await cache.disconnect()
    await engine.dispose()
    executor.shutdown(wait=False)


app = FastAPI(
    title="FaceDeep - Facial Recognition API",
    description="Facial Recognition API with ArcFace, ChromaDB, and Liveness Detection",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.ENVIRONMENT == "production" else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(APIVersioningMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(v1_router, prefix=settings.API_V1_PREFIX)
app.include_router(v2_router, prefix=settings.API_V2_PREFIX)


@app.get("/health", tags=["Health"])
async def health_check():
    from app.services.cache import cache
    from app.services.worker import worker_pool

    redis_ok = cache.available
    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "FaceDeep API",
        "version": "2.0.0",
        "redis": "connected" if redis_ok else "unavailable",
        "workers": worker_pool.stats,
    }
