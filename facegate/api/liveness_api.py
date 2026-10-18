"""REST liveness API (``/v1/liveness``) for apps that do not use an AWS SDK.

The same colour-flash liveness check as CreateFaceLivenessSession /
GetFaceLivenessSessionResults, behind plain JSON endpoints and an
``x-api-key`` header:

    POST /v1/liveness/sessions                  (api key)  start a session
    GET  /v1/liveness/capture?session=<id>                 hosted capture page
    GET  /v1/liveness/sessions/<id>/challenge              colours to flash
    POST /v1/liveness/sessions/<id>/frames                 upload the frames
    GET  /v1/liveness/sessions/<id>/result      (api key)  the verdict
    POST /v1/liveness/check                     (api key)  one-shot passive check:
                                                           photos, a selfie video or a ZIP

Sessions run in one of two modes: "flash" (default, random colour challenge)
or "passive" (plain frames, no colour flashes). /check is passive and
stateless: frames in, verdict out, nothing stored.

The device-side calls (capture page, challenge, frames) carry no key: the
session id is a random, single-use, short-lived capability, so the key never
has to be shipped inside a mobile app or web page. Only the app's backend (or
the tester) holding the key can start sessions and read verdicts, and the
device never learns the score.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from facegate.api.liveness_sessions import MAX_FRAME_BYTES, MAX_FRAMES, SessionError, _observe, get_challenge, submit_frames
from facegate.api.media import MediaError, frames_from_archive, frames_from_video
from facegate.api.operations import RequestContext
from facegate.config import Settings
from facegate.engine.liveness import judge_session
from facegate.engine.pipeline import ImageDecodeError, decode_image
from facegate.store.db import NotFound

CAPTURE_PAGE = Path(__file__).parent / "static" / "capture.html"
MAX_BODY_BYTES = 30 * 1024 * 1024
COLOUR_VALUES = {
    "white": "#FFFFFF", "red": "#FF0000", "green": "#00FF00", "blue": "#0000FF",
    "yellow": "#FFFF00", "cyan": "#00FFFF", "magenta": "#FF00FF",
}
FEEDBACK = {
    "FACE_NOT_VISIBLE": "The face was not visible in enough frames. Keep the whole face inside the oval for the full check.",
    "LOW_LIGHTING_DETECTED": "The face or the room is too dark. Move to a brighter place.",
    "HIGH_LIGHTING_DETECTED": "Strong light behind the person (for example a window). Turn so the light falls on the face.",
    "SCREEN_TOO_DIM": "The screen's colour flashes did not reach the face. Turn screen brightness up and hold the phone closer.",
    "FACE_TOO_FAR": "The face is too far from the screen. Move closer so the face fills the oval.",
    "MULTIPLE_FACES": "More than one face, or a different face, was seen during the check. Only one person should be in view.",
}
STATUS = {"SUCCEEDED": "COMPLETED"}
# When any of these is present an attack is suspected: give no hints on how
# to do better.
ATTACK_REASONS = {"SPOOF_FRAME_DETECTED", "NO_NATURAL_MOTION", "IDENTITY_CHANGED", "CHALLENGE_SEQUENCE_MISMATCH"}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


SESSION_ERRORS = {400: "INVALID_REQUEST", 404: "SESSION_NOT_FOUND", 409: "SESSION_NOT_AVAILABLE"}


def _session_err(exc: SessionError) -> JSONResponse:
    message = exc.message
    if exc.status == 409:
        message = "This session has already been used or has expired. Start a new session."
    elif exc.status == 404:
        message = "Unknown session."
    return _err(exc.status, SESSION_ERRORS.get(exc.status, "INVALID_REQUEST"), message)


def build_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/v1/liveness")

    def _caller(request: Request) -> str | JSONResponse:
        """Return the caller's key label, or an error response."""
        keys = settings.api_key_list
        if not keys:
            return _err(503, "API_DISABLED", "No API keys are configured on this server (FACEGATE_API_KEYS).")
        given = request.headers.get("x-api-key", "")
        for i, key in enumerate(keys, 1):
            if hmac.compare_digest(given.encode(), key.encode()):
                return f"api-key-{i}"
        return _err(401, "UNAUTHORIZED", "Missing or invalid x-api-key header.")

    def _base(request: Request) -> str:
        if settings.public_base_url:
            return settings.public_base_url.rstrip("/")
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        return f"{proto}://{host}"

    def _audit(request: Request, op: str, principal: str | None, status: str, t0: float, detail: dict | None = None) -> None:
        request.app.state.store.audit(
            str(uuid.uuid4()), op, principal, None, status, round((time.perf_counter() - t0) * 1000, 2), detail
        )

    # ------------------------------------------------------------- sessions
    @router.post("/sessions", status_code=201)
    async def create_session(request: Request):
        t0 = time.perf_counter()
        caller = _caller(request)
        if isinstance(caller, JSONResponse):
            return caller
        body: dict = {}
        raw = await request.body()
        if raw.strip():
            try:
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return _err(400, "INVALID_REQUEST", "Body must be a JSON object (or empty).")
        audit_images = body.get("auditImagesLimit", 0)
        if not isinstance(audit_images, int) or isinstance(audit_images, bool) or not 0 <= audit_images <= 4:
            return _err(400, "INVALID_REQUEST", "auditImagesLimit must be an integer from 0 to 4.")
        mode = body.get("mode", "flash")
        if mode not in ("flash", "passive"):
            return _err(400, "INVALID_REQUEST", 'mode must be "flash" or "passive".')
        reference = body.get("clientReference")
        if reference is not None and (not isinstance(reference, str) or len(reference) > 128):
            return _err(400, "INVALID_REQUEST", "clientReference must be a string of at most 128 characters.")

        service = request.app.state.service
        ctx = RequestContext(request_id=str(uuid.uuid4()), principal=caller)
        created = service.new_liveness_session(
            {"Settings": {"AuditImagesLimit": audit_images}, "ClientRequestToken": reference}, mode=mode
        )
        sid = created["SessionId"]
        sess = request.app.state.store.get_session(sid)
        base = _base(request)
        _audit(request, "v1.CreateLivenessSession", caller, "ok", t0, {"session": sid, "mode": mode})
        return {
            "sessionId": sid,
            "mode": mode,
            "status": "CREATED",
            "clientReference": reference,
            "expiresAt": _iso(sess["expires_at"]),
            "expiresInSeconds": settings.liveness_session_ttl_seconds,
            "challenge": _challenge_json(sess["challenge"]),
            "captureUrl": f"{base}/v1/liveness/capture?session={sid}",
            "challengeUrl": f"{base}/v1/liveness/sessions/{sid}/challenge",
            "framesUrl": f"{base}/v1/liveness/sessions/{sid}/frames",
            "resultUrl": f"{base}/v1/liveness/sessions/{sid}/result",
        }

    @router.get("/sessions/{session_id}/challenge")
    async def challenge(session_id: str, request: Request):
        try:
            c = get_challenge(request.app.state.store, session_id)
        except SessionError as exc:
            return _session_err(exc)
        return {
            "sessionId": session_id,
            "expiresAt": _iso(c["ExpiresAt"]),
            **_challenge_json({"colours": c["Colours"], "flash_ms": c["FlashMs"], "mode": c.get("Mode", "flash")}),
        }

    @router.post("/sessions/{session_id}/frames")
    async def frames(session_id: str, request: Request):
        t0 = time.perf_counter()
        if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
            return _err(413, "PAYLOAD_TOO_LARGE", "Upload at most 16 frames of at most 1.5 MB each.")
        try:
            body = json.loads(await request.body())
        except ValueError:
            return _err(400, "INVALID_REQUEST", "Body must be JSON.")
        items = body.get("frames", body.get("Frames")) if isinstance(body, dict) else None
        if not isinstance(items, list):
            return _err(400, "INVALID_REQUEST", "Body must be {\"frames\": [{\"colour\": ..., \"image\": <base64 JPEG>}, ...]}.")
        payload = {
            "Frames": [
                {"Colour": f.get("colour", f.get("Colour")), "Bytes": f.get("image", f.get("Bytes", ""))}
                if isinstance(f, dict) else {}
                for f in items
            ]
        }
        try:
            r = await run_in_threadpool(
                submit_frames, request.app.state.engine, request.app.state.store, settings, session_id, payload
            )
        except SessionError as exc:
            _audit(request, "v1.UploadLivenessFrames", None, f"error:{exc.status}", t0, {"session": session_id})
            return _session_err(exc)
        status = STATUS.get(r["Status"], r["Status"])
        _audit(request, "v1.UploadLivenessFrames", None, "ok", t0, {"session": session_id, "frames": len(items)})
        return {
            "sessionId": session_id,
            "status": status,
            "message": "Frames received. The result is available to your backend at the resultUrl.",
        }

    @router.get("/sessions/{session_id}/result")
    async def result(session_id: str, request: Request, includeReferenceImage: bool = False, includeAuditImages: bool = False):
        t0 = time.perf_counter()
        caller = _caller(request)
        if isinstance(caller, JSONResponse):
            return caller
        try:
            sess = request.app.state.store.get_session(session_id)
        except NotFound:
            return _err(404, "SESSION_NOT_FOUND", "Unknown session, or its result has already been deleted (results are kept for about an hour).")
        status = STATUS.get(sess["status"], sess["status"])
        if status in ("CREATED", "IN_PROGRESS") and sess["expires_at"] < time.time():
            status = "EXPIRED"
        threshold = settings.liveness_pass_confidence
        out: dict = {
            "sessionId": session_id,
            "mode": sess["challenge"].get("mode", "flash"),
            "status": status,
            "isLive": None,
            "confidence": None,
            "threshold": threshold,
            "feedback": [],
            "reasons": [],
            "clientReference": sess.get("client_token"),
            "createdAt": _iso(sess["created_at"]),
            "expiresAt": _iso(sess["expires_at"]),
        }
        if status in ("COMPLETED", "FAILED"):
            confidence = float(sess["confidence"] or 0.0)
            res = sess.get("result") or {}
            out["confidence"] = round(confidence, 2)
            out["isLive"] = status == "COMPLETED" and confidence >= threshold
            out["reasons"] = res.get("reasons", [])
            if not out["isLive"] and not ATTACK_REASONS.intersection(out["reasons"]):
                out["feedback"] = [{"code": c, "message": FEEDBACK.get(c, c)} for c in res.get("feedback") or []]
            ref = sess.get("reference")
            if includeReferenceImage and ref:
                out["referenceImage"] = {"image": ref["bytes"], "boundingBox": ref["box"]}
            if includeAuditImages and sess.get("audit"):
                out["auditImages"] = [{"image": a["bytes"], "boundingBox": a["box"]} for a in sess["audit"]]
        _audit(request, "v1.GetLivenessResult", caller, "ok", t0, {"session": session_id, "status": status, "confidence": out["confidence"]})
        return out

    # ------------------------------------------------- one-shot passive check
    @router.post("/check")
    async def check(request: Request, clientReference: str | None = None):
        """Passive liveness in one call. Accepts a burst of photos, a short
        selfie video, or a ZIP of frames (see _check_media). Stateless:
        nothing is stored, and no reference image is kept."""
        t0 = time.perf_counter()
        caller = _caller(request)
        if isinstance(caller, JSONResponse):
            return caller
        if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
            return _err(413, "PAYLOAD_TOO_LARGE", "The upload is larger than 30 MB.")
        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        try:
            images, source, reference = await run_in_threadpool(_check_media, content_type, await request.body(), clientReference)
        except UnsupportedMedia as exc:
            return _err(415, "UNSUPPORTED_MEDIA_TYPE", str(exc))
        except (binascii.Error, ImageDecodeError, MediaError, TypeError, ValueError) as exc:
            return _err(400, "INVALID_REQUEST", str(exc))

        engine = request.app.state.engine

        def analyse():
            obs = [_observe(engine, img, "none") for img in images]
            return judge_session(obs, frames_required=3, mode="passive")

        verdict = await run_in_threadpool(analyse)
        threshold = settings.liveness_pass_confidence
        confidence = round(float(verdict.confidence), 2)
        is_live = confidence >= threshold
        feedback = []
        if not is_live and not ATTACK_REASONS.intersection(verdict.reasons):
            feedback = [{"code": c, "message": FEEDBACK.get(c, c)} for c in verdict.feedback]
        _audit(request, "v1.LivenessCheck", caller, "ok", t0, {"frames": len(images), "source": source, "confidence": confidence, "mode": "passive"})
        return {
            "status": "COMPLETED",
            "mode": "passive",
            "isLive": is_live,
            "confidence": confidence,
            "threshold": threshold,
            "feedback": feedback,
            "reasons": verdict.reasons,
            "source": source,
            "framesAnalysed": len(images),
            "clientReference": reference,
        }

    # --------------------------------------------------------- capture page
    @router.get("/capture", response_class=HTMLResponse)
    async def capture_page():
        return HTMLResponse(CAPTURE_PAGE.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})

    return router


class UnsupportedMedia(ValueError):
    pass


FRAMES_HELP = 'Send {"frames": [{"image": <base64 JPEG>}, ...]} (3-16 photos), {"video": <base64 MP4/MOV/WebM>}, {"archive": <base64 ZIP of frames>}, or the raw file with Content-Type video/mp4, video/quicktime, video/webm or application/zip.'


def _check_media(content_type: str, body: bytes, reference: str | None) -> tuple[list, str, str | None]:
    """Decode the /check upload into frames. Returns (frames, source, clientReference)."""
    if content_type.startswith("video/"):
        return frames_from_video(body), "video", _reference(reference)
    if content_type in ("application/zip", "application/x-zip-compressed"):
        return frames_from_archive(body), "archive", _reference(reference)
    if content_type not in ("application/json", ""):
        raise UnsupportedMedia(FRAMES_HELP)
    try:
        req = json.loads(body)
    except ValueError as exc:
        raise ValueError(FRAMES_HELP) from exc
    if not isinstance(req, dict):
        raise ValueError(FRAMES_HELP)
    reference = _reference(req.get("clientReference", reference))
    if isinstance(req.get("video"), str):
        return frames_from_video(base64.b64decode(req["video"], validate=True)), "video", reference
    if isinstance(req.get("archive"), str):
        return frames_from_archive(base64.b64decode(req["archive"], validate=True)), "archive", reference
    items = req.get("frames")
    if not isinstance(items, list) or not 3 <= len(items) <= MAX_FRAMES:
        raise ValueError(FRAMES_HELP)
    images = []
    for f in items:
        raw = base64.b64decode(f.get("image", "") if isinstance(f, dict) else "", validate=True)
        if not raw or len(raw) > MAX_FRAME_BYTES:
            raise ValueError("Each frame must be a base64 JPEG or PNG of at most 1.5 MB.")
        images.append(decode_image(raw))
    return images, "frames", reference


def _reference(value) -> str | None:
    if value is not None and (not isinstance(value, str) or len(value) > 128):
        raise ValueError("clientReference must be a string of at most 128 characters.")
    return value


def _challenge_json(c: dict) -> dict:
    colours = c["colours"]
    if c.get("mode") == "passive":
        return {"mode": "passive", "colours": [], "colourValues": {}, "captureIntervalMs": c["flash_ms"], "framesRequired": len(colours)}
    return {
        "mode": "flash",
        "colours": colours,
        "colourValues": {name: COLOUR_VALUES[name] for name in dict.fromkeys(colours)},
        "flashMs": c["flash_ms"],
        "framesRequired": len(colours),
    }
