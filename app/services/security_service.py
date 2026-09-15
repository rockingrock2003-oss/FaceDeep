import hashlib
import hmac
import ipaddress
import logging
import time

from fastapi import HTTPException, status

from app.db import AsyncSessionLocal
from app.models.audit_log import AuditLog

logger = logging.getLogger("facedeep.security")


class SecurityService:
    async def rotate_api_key(self, user, db, grace_period_hours: int = 24) -> dict:
        from app.core.security import generate_api_key

        old_prefix = user.api_key_prefix

        raw_key, key_hash, key_prefix = generate_api_key()
        user.api_key_hash = key_hash
        user.api_key_prefix = key_prefix
        await db.commit()

        await self.log_audit(
            user_id=user.id,
            action="api_key.rotated",
            resource_type="user",
            resource_id=user.id,
            details=f"Old prefix: {old_prefix}",
        )

        return {
            "api_key": raw_key,
            "api_key_prefix": key_prefix,
            "old_prefix": old_prefix,
            "grace_period_hours": grace_period_hours,
            "message": "Store this key securely. It won't be shown again.",
        }

    def validate_ip_allowlist(self, ip: str, allowed_cidrs: list[str]) -> bool:
        if not allowed_cidrs:
            return True
        try:
            client_ip = ipaddress.ip_address(ip)
            return any(
                client_ip in ipaddress.ip_network(cidr, strict=False)
                for cidr in allowed_cidrs
            )
        except ValueError:
            return False

    def compute_request_signature(
        self, method: str, path: str, body: bytes, timestamp: str, secret: str
    ) -> str:
        string_to_sign = f"{method}\n{path}\n{timestamp}\n{hashlib.sha256(body).hexdigest()}"
        return hmac.new(
            secret.encode(), string_to_sign.encode(), hashlib.sha256
        ).hexdigest()

    def verify_request_signature(
        self,
        method: str,
        path: str,
        body: bytes,
        timestamp: str,
        signature: str,
        secret: str,
        max_age: int = 300,
    ) -> bool:
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > max_age:
                return False
        except (ValueError, TypeError):
            return False

        expected = self.compute_request_signature(method, path, body, timestamp, secret)
        return hmac.compare_digest(expected, signature)

    async def log_audit(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        details: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ):
        try:
            async with AsyncSessionLocal() as db:
                log = AuditLog(
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details=details,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                db.add(log)
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")


security_service = SecurityService()
