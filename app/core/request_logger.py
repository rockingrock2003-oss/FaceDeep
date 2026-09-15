import asyncio
import hashlib
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("facedeep.middleware")

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

RATE_LIMIT_PATHS = {"/face/recognize", "/face/ismatch", "/face/delete", "/face/enroll", "/face/bulk-enroll"}


def _extract_user_id_from_token(auth_header: str) -> str | None:
    try:
        from jose import jwt
        from app.core.config import settings

        token = auth_header[7:]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except Exception:
        return None


async def _extract_user_info(request: Request) -> tuple[str | None, str | None]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        user_id = _extract_user_id_from_token(auth_header)
        if user_id:
            return user_id, None

    api_key = request.headers.get("X-API-Key")
    if api_key:
        try:
            from app.db import AsyncSessionLocal
            from app.models import User
            from sqlalchemy import select

            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User.id, User.plan).where(User.api_key_hash == key_hash)
                )
                row = result.one_or_none()
                if row:
                    return row[0], row[1]
        except Exception:
            pass

    return None, None


async def _log_request(
    user_id: str,
    method: str,
    endpoint: str,
    status_code: int,
    response_time_ms: float,
):
    try:
        from app.db import AsyncSessionLocal
        from app.models.api_request_log import ApiRequestLog
        from app.services.cache import cache

        async with AsyncSessionLocal() as session:
            log = ApiRequestLog(
                user_id=user_id,
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                response_time_ms=response_time_ms,
                created_at=datetime.now(UTC),
            )
            session.add(log)
            await session.commit()

        await cache.delete(f"stats:{user_id}")
    except Exception as e:
        logger.warning(f"Failed to log API request: {e}")


LOG_PATHS = {"/face/recognize", "/face/ismatch", "/face/delete", "/face/enroll", "/face/bulk-enroll"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(request_id)

        path = request.url.path
        should_rate_limit = any(path.endswith(p) for p in RATE_LIMIT_PATHS)
        should_log = should_rate_limit

        rate_limit_headers = {}
        if should_rate_limit:
            api_key = request.headers.get("X-API-Key")
            if api_key:
                from app.services.rate_limiter import rate_limiter
                user_id, plan = await _extract_user_info(request)
                if plan:
                    try:
                        result = await rate_limiter.check_and_consume(api_key, plan, request)
                        rate_limit_headers = rate_limiter.get_headers(result)
                    except Exception:
                        pass

        start = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        for k, v in rate_limit_headers.items():
            response.headers[k] = v

        logger.info(
            f"[{request_id}] {request.method} {path} -> {response.status_code} ({duration_ms}ms)"
        )

        if should_log:
            user_id, _ = await _extract_user_info(request)
            if user_id:
                asyncio.create_task(
                    _log_request(
                        user_id=user_id,
                        method=request.method,
                        endpoint=path,
                        status_code=response.status_code,
                        response_time_ms=duration_ms,
                    )
                )

        return response
