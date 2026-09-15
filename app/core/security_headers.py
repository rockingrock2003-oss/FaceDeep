import ipaddress
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("facedeep.security")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        return response


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_cidrs: list[str] | None = None):
        super().__init__(app)
        self.allowed_cidrs = allowed_cidrs or []

    async def dispatch(self, request: Request, call_next):
        if not self.allowed_cidrs:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        try:
            ip = ipaddress.ip_address(client_ip)
            allowed = any(
                ip in ipaddress.ip_network(cidr, strict=False)
                for cidr in self.allowed_cidrs
            )
        except ValueError:
            allowed = False

        if not allowed:
            logger.warning(f"IP {client_ip} not in allowlist")
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=403,
                content={"detail": "IP address not allowed"},
            )

        return await call_next(request)
