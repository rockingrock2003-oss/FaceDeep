import json
import logging
from datetime import UTC, datetime

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User

logger = logging.getLogger("facedeep.residency")

SUPPORTED_REGIONS = ["us", "eu", "ap"]

REGION_CONFIG = {
    "us": {
        "name": "United States",
        "data_retention_days": 90,
        "gdpr_applicable": False,
    },
    "eu": {
        "name": "European Union",
        "data_retention_days": 365,
        "gdpr_applicable": True,
    },
    "ap": {
        "name": "Asia Pacific",
        "data_retention_days": 90,
        "gdpr_applicable": False,
    },
}


class DataResidencyService:
    def get_region_config(self, region: str) -> dict | None:
        return REGION_CONFIG.get(region)

    def list_regions(self) -> list[dict]:
        return [{"id": k, **v} for k, v in REGION_CONFIG.items()]

    async def set_org_region(
        self,
        db: AsyncSession,
        user: User,
        organization_id: str,
        region: str,
    ) -> dict:
        if region not in SUPPORTED_REGIONS:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported region: {region}. Supported: {SUPPORTED_REGIONS}",
            )

        from app.models.organization import Organization

        stmt = select(Organization).where(
            Organization.id == organization_id,
            Organization.owner_id == user.id,
        )
        result = await db.execute(stmt)
        org = result.scalar_one_or_none()

        if not org:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found or you are not the owner",
            )

        org.region = region
        await db.commit()

        logger.info(
            f"Organization {organization_id} region set to {region} by user {user.id}"
        )

        return {
            "organization_id": organization_id,
            "region": region,
            "config": REGION_CONFIG[region],
            "updated_at": datetime.now(UTC).isoformat(),
        }

    async def get_org_region(self, db: AsyncSession, organization_id: str) -> dict:
        from app.models.organization import Organization

        stmt = select(Organization).where(Organization.id == organization_id)
        result = await db.execute(stmt)
        org = result.scalar_one_or_none()

        if not org:
            return {"region": "us", "config": REGION_CONFIG["us"]}

        region = getattr(org, "region", "us") or "us"
        return {"region": region, "config": REGION_CONFIG.get(region, REGION_CONFIG["us"])}


data_residency_service = DataResidencyService()
