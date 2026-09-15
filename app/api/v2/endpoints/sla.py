import platform
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import metrics
from app.db import get_db
from app.models import User
from app.models.api_request_log import ApiRequestLog

router = APIRouter(tags=["SLA & Reliability"])

_start_time = time.time()


@router.get("/status")
async def status_page():
    uptime = round(time.time() - _start_time, 2)
    return {
        "service": "FaceDeep API",
        "status": "operational",
        "uptime_seconds": uptime,
        "current_version": settings.API_LATEST_VERSION,
        "supported_versions": ["v1", "v2"],
        "incident_history": [],
        "last_updated": datetime.now(UTC).isoformat(),
    }


@router.get("/sla")
async def get_sla():
    return {
        "uptime_sla": "99.9%",
        "max_downtime_per_year": "8.76 hours",
        "response_time_sla": {
            "recognize_p99": "< 500ms",
            "health_p99": "< 200ms",
        },
        "incident_response": {
            "P1": "Within 15 minutes",
            "P2": "Within 1 hour",
        },
        "data_retention": {
            "images": "90 days",
            "embeddings": "Indefinite",
            "audit_logs": "1 year",
            "request_logs": "90 days",
        },
        "support": {
            "free": "Email support",
            "starter": "Priority email support",
            "pro": "24/7 email + chat support",
            "enterprise": "Dedicated support with SLA",
        },
    }


@router.get("/data-retention")
async def get_data_retention():
    return {
        "policies": [
            {
                "data_type": "Images",
                "retention_days": 90,
                "description": "Uploaded face images are stored for 90 days then deleted",
            },
            {
                "data_type": "Embeddings",
                "retention_days": -1,
                "description": "Face embeddings are retained indefinitely",
            },
            {
                "data_type": "Audit Logs",
                "retention_days": 365,
                "description": "API audit logs are retained for 1 year",
            },
            {
                "data_type": "Request Logs",
                "retention_days": 90,
                "description": "API request logs are retained for 90 days",
            },
            {
                "data_type": "Webhook Deliveries",
                "retention_days": 30,
                "description": "Webhook delivery logs retained for 30 days",
            },
        ]
    }


@router.get("/compliance")
async def get_compliance():
    return {
        "frameworks": [
            {
                "name": "SOC 2 Type II",
                "status": "In Progress",
                "description": "Service Organization Control 2 Type II audit",
            },
            {
                "name": "GDPR",
                "status": "Compliant",
                "description": "General Data Protection Regulation compliance",
            },
            {
                "name": "CCPA",
                "status": "Compliant",
                "description": "California Consumer Privacy Act compliance",
            },
        ],
        "data_processing": {
            "dpa_available": True,
            "subprocessors": ["PostgreSQL", "Redis", "ChromaDB", "Stripe"],
            "data_residency": "Configurable per deployment",
            "right_to_deletion": "Supported via /api/v2/face/clear",
        },
    }


@router.get("/incidents")
async def list_incidents():
    return {
        "status": "success",
        "incidents": [],
        "message": "No active incidents",
    }
