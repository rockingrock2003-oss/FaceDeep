from fastapi import APIRouter

from app.api.v2.endpoints.billing import router as billing_router
from app.api.v2.endpoints.face import router as face_router
from app.api.v2.endpoints.observability import router as observability_router
from app.api.v2.endpoints.organizations import router as org_router
from app.api.v2.endpoints.sla import router as sla_router
from app.api.v2.endpoints.sso import router as sso_router
from app.api.v2.endpoints.upload import router as upload_router
from app.api.v2.endpoints.webhooks import router as webhook_router
from app.api.v2.endpoints.admin import router as admin_router
from app.api.v2.endpoints.analytics import router as analytics_router

api_router = APIRouter()
api_router.include_router(face_router)
api_router.include_router(upload_router)
api_router.include_router(webhook_router)
api_router.include_router(billing_router)
api_router.include_router(observability_router)
api_router.include_router(org_router)
api_router.include_router(sla_router)
api_router.include_router(sso_router)
api_router.include_router(admin_router)
api_router.include_router(analytics_router)
