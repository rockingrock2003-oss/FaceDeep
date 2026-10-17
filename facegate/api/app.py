"""HTTP layer.

``POST /`` speaks the AWS JSON 1.1 protocol used by every Rekognition SDK:

    POST / HTTP/1.1
    X-Amz-Target: RekognitionService.SearchFacesByImage
    Content-Type: application/x-amz-json-1.1
    Authorization: AWS4-HMAC-SHA256 Credential=...

Point any AWS SDK at this server with ``endpoint_url`` and it works unchanged.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.concurrency import run_in_threadpool

from facegate import __version__
from facegate.api import errors
from facegate.api.liveness_api import build_router
from facegate.api.liveness_sessions import SessionError, get_challenge, submit_frames
from facegate.api.operations import RekognitionService, RequestContext
from facegate.api.sigv4 import SignatureError, verify
from facegate.config import Settings, get_settings
from facegate.engine.pipeline import FaceEngine
from facegate.store.crypto import load_cipher
from facegate.store.db import FaceStore

log = logging.getLogger("facegate")

REQUESTS = Counter("facegate_requests_total", "Rekognition API requests", ["operation", "status"])
LATENCY = Histogram(
    "facegate_request_seconds",
    "Server-side latency per operation",
    ["operation"],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0, 2.5),
)
DECISIONS = Counter("facegate_search_decisions_total", "Search outcomes", ["decision"])

JSON_11 = "application/x-amz-json-1.1"


def _error(exc: errors.RekognitionError | SignatureError, request_id: str) -> Response:
    code = exc.code
    body = {"__type": code, "message": exc.message, "Message": exc.message}
    return Response(
        content=json.dumps(body),
        status_code=exc.status,
        media_type=JSON_11,
        headers={"x-amzn-RequestId": request_id, "x-amzn-ErrorType": code},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = FaceEngine(settings)
        cipher = load_cipher(settings.data_key, settings.data_dir, settings.environment)
        store = FaceStore(settings.data_dir / "facegate.db", cipher, engine.model_id)
        app.state.engine = engine
        app.state.store = store
        app.state.service = RekognitionService(settings, engine, store)
        if settings.auth_mode == "none":
            log.warning("FACEGATE_AUTH_MODE=none - requests are NOT authenticated")
        elif not settings.credential_map:
            log.warning("No FACEGATE_CREDENTIALS configured - every signed request will be rejected")
        stats = store.stats()
        if stats["stale_faces"]:
            log.warning("%d faces were enrolled with a different model; run POST /admin/reindex", stats["stale_faces"])
        log.info("FaceGate %s ready: model=%s calibration=%s %s", __version__, engine.model_id, engine.calibration.source, stats)
        housekeeping = asyncio.create_task(_housekeeping(store))
        yield
        housekeeping.cancel()
        store.close()

    async def _housekeeping(store: FaceStore) -> None:
        """Delete expired liveness sessions (and their encrypted images) and
        old audit rows, every 10 minutes."""
        while True:
            try:
                sessions = await run_in_threadpool(store.purge_expired_sessions, settings.liveness_session_retention_seconds)
                audits = await run_in_threadpool(store.purge_audit, settings.audit_retention_days) if settings.audit_retention_days > 0 else 0
                if sessions or audits:
                    log.info("Housekeeping: deleted %d liveness sessions, %d audit rows", sessions, audits)
            except Exception:
                log.exception("Housekeeping failed")
            await asyncio.sleep(600)

    app = FastAPI(title="FaceGate", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type", "x-api-key"],
        expose_headers=["x-facegate-liveness", "x-facegate-decision"],
    )

    app.include_router(build_router(settings))

    # ------------------------------------------------------------ Rekognition
    @app.post("/")
    async def rekognition(request: Request) -> Response:
        t0 = time.perf_counter()
        request_id = str(uuid.uuid4())
        body = await request.body()
        target = request.headers.get("x-amz-target", "")
        prefix, _, operation = target.partition(".")
        service: RekognitionService = request.app.state.service
        ctx = RequestContext(request_id=request_id)
        status = "ok"
        try:
            if prefix != "RekognitionService" or operation not in service.handlers:
                raise errors.UnknownOperationException(f"Unknown operation {target!r}")
            if settings.auth_mode == "sigv4":
                principal = verify(
                    method=request.method,
                    path=request.url.path,
                    query=request.url.query,
                    headers=dict(request.headers),
                    body=body,
                    credentials=settings.credential_map,
                    max_skew_seconds=settings.max_clock_skew_seconds,
                )
                ctx.principal = principal.access_key_id
            try:
                req = json.loads(body or b"{}")
                if not isinstance(req, dict):
                    raise ValueError
            except ValueError as exc:
                raise errors.InvalidParameterException("Request body is not valid JSON") from exc
            result = await run_in_threadpool(service.handlers[operation], req, ctx)
            elapsed = (time.perf_counter() - t0) * 1000
            headers = {
                "x-amzn-RequestId": request_id,
                "x-facegate-model": request.app.state.engine.model_id,
                "x-facegate-server-ms": f"{elapsed:.1f}",
                **ctx.headers,
            }
            if "decision" in ctx.detail:
                DECISIONS.labels(ctx.detail["decision"]).inc()
            return Response(content=json.dumps(result), media_type=JSON_11, headers=headers)
        except (errors.RekognitionError, SignatureError) as exc:
            status = exc.code
            return _error(exc, request_id)
        except Exception:
            log.exception("Unhandled error in %s", operation)
            status = "InternalServerError"
            return _error(errors.InternalServerError("Internal server error"), request_id)
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            op = operation or "unknown"
            REQUESTS.labels(op, status).inc()
            LATENCY.labels(op).observe(elapsed / 1000)
            request.app.state.store.audit(request_id, op, ctx.principal, ctx.collection_id, status, round(elapsed, 2), ctx.detail or None)

    # ------------------------------------------------- liveness (device side)
    @app.get("/liveness/sessions/{session_id}/challenge")
    async def liveness_challenge(session_id: str, request: Request):
        try:
            return get_challenge(request.app.state.store, session_id)
        except SessionError as exc:
            return JSONResponse({"message": exc.message}, status_code=exc.status)

    @app.post("/liveness/sessions/{session_id}/frames")
    async def liveness_frames(session_id: str, request: Request):
        try:
            payload = json.loads(await request.body())
        except ValueError:
            return JSONResponse({"message": "Body must be JSON"}, status_code=400)
        try:
            return await run_in_threadpool(
                submit_frames, request.app.state.engine, request.app.state.store, settings, session_id, payload
            )
        except SessionError as exc:
            return JSONResponse({"message": exc.message}, status_code=exc.status)

    # ------------------------------------------------------------ operations
    @app.get("/health")
    async def health(request: Request):
        engine: FaceEngine = request.app.state.engine
        return {
            "status": "ok",
            "version": __version__,
            "model": engine.model_id,
            "calibration": engine.calibration.source,
            "passive_liveness": engine.liveness.available,
            **request.app.state.store.stats(),
        }

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # ----------------------------------------------------------------- admin
    def _admin(request: Request) -> JSONResponse | None:
        token = settings.admin_token
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not token or not hmac.compare_digest(token, given):
            return JSONResponse({"message": "Forbidden"}, status_code=403)
        return None

    @app.get("/admin/lookalikes")
    async def admin_lookalikes(request: Request, collection_id: str | None = None):
        if (denied := _admin(request)) is not None:
            return denied
        return {"Lookalikes": request.app.state.store.list_lookalikes(collection_id)}

    @app.get("/admin/audit")
    async def admin_audit(request: Request, limit: int = 100):
        if (denied := _admin(request)) is not None:
            return denied
        return {"Events": request.app.state.store.recent_audit(min(limit, 1000))}

    @app.get("/admin/calibration")
    async def admin_calibration(request: Request):
        if (denied := _admin(request)) is not None:
            return denied
        engine: FaceEngine = request.app.state.engine
        return {"Source": engine.calibration.source, "Anchors": engine.calibration.describe()}

    @app.post("/admin/reindex")
    async def admin_reindex(request: Request):
        """Re-embed every stored face crop with the current model (model upgrade)."""
        if (denied := _admin(request)) is not None:
            return denied
        from facegate.store.reindex import reindex_all

        return await run_in_threadpool(reindex_all, request.app.state.engine, request.app.state.store)

    return app
