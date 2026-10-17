"""The REST liveness API (/v1/liveness): what a mobile app integrates with."""

from __future__ import annotations

import base64
import time

import cv2
import httpx
import numpy as np

from tests.conftest import API_KEY, image

KEY = {"x-api-key": API_KEY}


def _start(server, **body) -> dict:
    r = httpx.post(f"{server['url']}/v1/liveness/sessions", headers=KEY, json=body or None)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_session_requires_api_key(server):
    url = f"{server['url']}/v1/liveness/sessions"
    assert httpx.post(url).status_code == 401
    r = httpx.post(url, headers={"x-api-key": "wrong"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


def test_create_session_shape(server):
    s = _start(server, clientReference="user-42")
    assert s["status"] == "CREATED" and s["clientReference"] == "user-42"
    ch = s["challenge"]
    assert ch["framesRequired"] == len(ch["colours"]) == 7
    assert ch["colours"][0] == ch["colours"][3] == ch["colours"][6] == "white"
    assert all(ch["colours"][i] != ch["colours"][i + 1] for i in range(6))
    assert set(ch["colourValues"]) == set(ch["colours"]) and ch["flashMs"] > 0
    assert s["captureUrl"].endswith(f"/v1/liveness/capture?session={s['sessionId']}")
    for k in ("challengeUrl", "framesUrl", "resultUrl", "expiresAt"):
        assert k in s
    # Device side: the challenge needs no key.
    c = httpx.get(s["challengeUrl"]).json()
    assert c["colours"] == ch["colours"]


def test_invalid_create_body(server):
    r = httpx.post(f"{server['url']}/v1/liveness/sessions", headers=KEY, json={"auditImagesLimit": 9})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_still_photo_replay_is_not_live_and_session_is_single_use(server):
    s = _start(server, auditImagesLimit=1)
    still = base64.b64encode(image("George_W_Bush_0001.jpg")).decode()
    frames = [{"colour": c, "image": still} for c in s["challenge"]["colours"]]
    up = httpx.post(s["framesUrl"], json={"frames": frames}, timeout=60)
    assert up.status_code == 200, up.text
    assert up.json()["status"] == "COMPLETED"
    assert "confidence" not in up.json()  # the device never sees the score
    # Pending result needs the key.
    assert httpx.get(s["resultUrl"]).status_code == 401
    r = httpx.get(s["resultUrl"], headers=KEY, params={"includeReferenceImage": "true", "includeAuditImages": "true"}).json()
    assert r["status"] == "COMPLETED"
    assert r["isLive"] is False and r["confidence"] < 50
    assert "NO_NATURAL_MOTION" in r["reasons"]
    assert base64.b64decode(r["referenceImage"]["image"])[:3] == b"\xff\xd8\xff"
    assert len(r["auditImages"]) == 1
    # Single use.
    again = httpx.post(s["framesUrl"], json={"frames": frames}, timeout=60)
    assert again.status_code == 409 and again.json()["error"]["code"] == "SESSION_NOT_AVAILABLE"
    assert httpx.get(s["challengeUrl"]).status_code == 409


def test_dark_capture_returns_feedback(server):
    s = _start(server)
    base = cv2.imdecode(np.frombuffer(image("George_W_Bush_0001.jpg"), np.uint8), cv2.IMREAD_COLOR)
    rng = np.random.default_rng(0)
    frames = []
    for k, c in enumerate(s["challenge"]["colours"]):
        f = np.clip(np.roll(base, k * 2, axis=1).astype(np.float32) * 0.18 + rng.normal(0, 1.0, base.shape), 0, 255).astype(np.uint8)
        frames.append({"colour": c, "image": base64.b64encode(cv2.imencode(".jpg", f)[1].tobytes()).decode()})
    assert httpx.post(s["framesUrl"], json={"frames": frames}, timeout=60).status_code == 200
    r = httpx.get(s["resultUrl"], headers=KEY).json()
    assert r["isLive"] is False
    assert "LOW_LIGHTING_DETECTED" in [f["code"] for f in r["feedback"]]
    assert all(f["message"] for f in r["feedback"])


def test_bad_frames_and_unknown_session(server):
    s = _start(server)
    r = httpx.post(s["framesUrl"], json={"nope": 1})
    assert r.status_code == 400
    r = httpx.post(s["framesUrl"], json={"frames": [{"colour": "white", "image": "not base64!"}]})
    assert r.status_code == 400
    assert httpx.get(s["resultUrl"], headers=KEY).json()["status"] == "FAILED"
    missing = f"{server['url']}/v1/liveness/sessions/00000000-0000-4000-8000-000000000000"
    assert httpx.get(f"{missing}/result", headers=KEY).status_code == 404
    assert httpx.get(f"{missing}/challenge").status_code == 404


def test_pending_session_result(server):
    s = _start(server)
    r = httpx.get(s["resultUrl"], headers=KEY).json()
    assert r["status"] == "CREATED" and r["isLive"] is None and r["confidence"] is None


def test_capture_page_served(server):
    r = httpx.get(f"{server['url']}/v1/liveness/capture?session=abc")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "/v1/liveness/sessions/" in r.text and "getUserMedia" in r.text


def test_housekeeping_purges_old_sessions_and_audit(tmp_path):
    from facegate.store.crypto import Cipher
    from facegate.store.db import FaceStore

    store = FaceStore(tmp_path / "t.db", Cipher(b"k" * 32), "m")
    store.create_session("s-old", ttl=-7200, client_token=None, settings={}, challenge={"colours": []})
    store.create_session("s-new", ttl=180, client_token=None, settings={}, challenge={"colours": []})
    assert store.purge_expired_sessions(3600) == 1
    store.get_session("s-new")
    store.audit("r1", "op", None, None, "ok", 1.0, None)
    store._x("UPDATE audit_log SET ts = ?", (time.time() - 100 * 86400,))
    assert store.purge_audit(90) == 1
    store.close()
