from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.face import router as face_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(face_router)
