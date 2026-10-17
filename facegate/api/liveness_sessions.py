"""Device-facing half of the liveness session flow.

In AWS, the device streams video to Rekognition using the Amplify
FaceLivenessDetector component, then the backend calls
GetFaceLivenessSessionResults. Here the device fetches the challenge and
uploads the captured frames over plain HTTPS; the backend side
(CreateFaceLivenessSession / GetFaceLivenessSessionResults) is identical to
Rekognition's API.

The session id acts as a short-lived, single-use capability: it is random
(UUIDv4), expires after a few minutes and can only be submitted once.
"""

from __future__ import annotations

import base64
import binascii
import json
import random
import time

import cv2
import numpy as np

from facegate.api import shapes
from facegate.config import Settings
from facegate.engine.embedder import align_face
from facegate.engine.liveness import FrameObservation, judge_session
from facegate.engine.pipeline import FaceEngine, ImageDecodeError, decode_image
from facegate.store.db import FaceStore, NotFound

MAX_FRAMES = 16
MAX_FRAME_BYTES = 1_500_000


class SessionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def get_challenge(store: FaceStore, session_id: str) -> dict:
    try:
        sess = store.get_session(session_id)
    except NotFound as exc:
        raise SessionError(404, "Session not found") from exc
    if sess["status"] != "CREATED" or sess["expires_at"] < time.time():
        raise SessionError(409, f"Session is {sess['status'] if sess['expires_at'] >= time.time() else 'EXPIRED'}")
    c = sess["challenge"]
    return {
        "SessionId": session_id,
        "Challenge": {"Type": c["type"], "Version": c["version"]},
        "Colours": c["colours"],
        "FlashMs": c["flash_ms"],
        "ExpiresAt": sess["expires_at"],
    }


def _observe(engine: FaceEngine, img: np.ndarray, colour: str) -> FrameObservation:
    faces = engine.detector.detect(img)
    obs = FrameObservation(colour=colour, face_count=len(faces))
    if len(faces) != 1:
        return obs
    d = faces[0]
    aligned = align_face(img, d.landmarks)
    # Identity check on a grey copy so the coloured flash does not move the template.
    grey3 = cv2.cvtColor(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    obs.embedding = engine.embedder.embed(grey3, flip=False)  # same-person check only: one pass is enough
    obs.passive = engine.liveness.score(img, d.box)
    obs.face_bgr = aligned[30:100, 24:88].reshape(-1, 3).mean(axis=0)
    obs.landmarks = d.landmarks
    obs.box = d.box
    x, y, w, h = (int(v) for v in d.box)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    obs.gray_small = cv2.resize(gray[y : y + h, x : x + w], (64, 64))
    # Lighting: inner face region vs the rest of the frame (backlight check).
    fx, fy, fw, fh = x + w // 4, y + h // 4, max(1, w // 2), max(1, h // 2)
    face_sum = float(gray[fy : fy + fh, fx : fx + fw].sum())
    face_n = gray[fy : fy + fh, fx : fx + fw].size
    box_sum = float(gray[y : y + h, x : x + w].sum())
    rest_n = gray.size - gray[y : y + h, x : x + w].size
    obs.face_luma = face_sum / max(face_n, 1)
    obs.background_luma = (float(gray.sum()) - box_sum) / max(rest_n, 1)
    obs._det = d  # type: ignore[attr-defined]
    obs._img = img  # type: ignore[attr-defined]
    return obs


def _debug_save(root, session_id: str, observations: list[FrameObservation], verdict, result: dict) -> None:
    """Opt-in diagnostics (FACEGATE_DEBUG_PROBE_DIR): every frame + the verdict."""
    try:
        d = root / f"{time.strftime('%Y%m%d-%H%M%S')}-session-{session_id[:8]}"
        d.mkdir(parents=True, exist_ok=True)
        frames = []
        for i, o in enumerate(observations):
            img = getattr(o, "_img", None)
            if img is not None:
                cv2.imwrite(str(d / f"{i:02d}-{o.colour}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            frames.append({"i": i, "colour": o.colour, "faces": o.face_count, "passive": o.passive})
        (d / "verdict.json").write_text(
            json.dumps({"confidence": verdict.confidence, **result, "frames": frames}, indent=2, default=str)
        )
    except Exception:
        pass


def submit_frames(engine: FaceEngine, store: FaceStore, settings: Settings, session_id: str, payload: dict) -> dict:
    frames = payload.get("Frames")
    if not isinstance(frames, list) or not frames:
        raise SessionError(400, "Frames is required")
    if len(frames) > MAX_FRAMES:
        raise SessionError(400, f"At most {MAX_FRAMES} frames")
    try:
        sess = store.get_session(session_id)
    except NotFound as exc:
        raise SessionError(404, "Session not found") from exc
    expected = sess["challenge"]["colours"]
    if not store.claim_session(session_id):
        raise SessionError(409, "Session already used or expired")

    observations: list[FrameObservation] = []
    try:
        for i, fr in enumerate(frames):
            colour = fr.get("Colour")
            if i < len(expected) and colour != expected[i]:
                # The device must replay *our* random sequence, in order.
                colour = "mismatch"
            raw = base64.b64decode(fr.get("Bytes", ""), validate=True)
            if len(raw) > MAX_FRAME_BYTES:
                raise SessionError(400, "Frame too large")
            observations.append(_observe(engine, decode_image(raw), colour))
    except (binascii.Error, ImageDecodeError, TypeError, ValueError) as exc:
        store.finish_session(session_id, "FAILED", 0.0, {"reasons": ["INVALID_FRAME"], "error": str(exc)}, None, None)
        raise SessionError(400, "Invalid frame data") from exc

    verdict = judge_session(observations, settings.liveness_frames_required)
    if any(o.colour == "mismatch" for o in observations):
        verdict.reasons.append("CHALLENGE_SEQUENCE_MISMATCH")
        verdict.confidence = min(verdict.confidence, 10.0)

    usable = [o for o in observations if o.face_count == 1]
    reference, audit = None, None
    if usable:
        whites = [o for o in usable if o.colour == "white"] or usable
        best = max(whites, key=lambda o: (o._det.score, o.passive or 0))  # type: ignore[attr-defined]

        def pack(o: FrameObservation) -> dict:
            ok, buf = cv2.imencode(".jpg", o._img, [cv2.IMWRITE_JPEG_QUALITY, 92])  # type: ignore[attr-defined]
            h, w = o._img.shape[:2]  # type: ignore[attr-defined]
            return {"bytes": base64.b64encode(buf.tobytes()).decode(), "box": shapes.bounding_box(o.box, w, h)}

        reference = pack(best)
        limit = int(sess["settings"].get("AuditImagesLimit") or 0)
        others = [o for o in usable if o is not best]
        if limit and others:
            audit = [pack(o) for o in random.sample(others, min(limit, len(others)))]

    status = "SUCCEEDED" if usable else "FAILED"
    result = {"reasons": verdict.reasons, "components": verdict.components, "feedback": verdict.feedback}
    if settings.debug_probe_dir is not None:
        _debug_save(settings.debug_probe_dir, session_id, observations, verdict, result)
    store.finish_session(session_id, status, verdict.confidence, result, reference, audit)
    # The device only learns that the upload completed; the verdict goes to
    # the backend via GetFaceLivenessSessionResults (as with Rekognition).
    return {"SessionId": session_id, "Status": status}
