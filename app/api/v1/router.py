from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.billing import router as billing_router
from app.api.v1.endpoints.face import router as face_router
from app.api.v1.endpoints.oauth import router as oauth_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(oauth_router)
api_router.include_router(face_router)
api_router.include_router(billing_router)
