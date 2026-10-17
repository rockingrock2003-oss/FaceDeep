"""Mock attendance backend - stands in for the company's existing app.

It talks to face recognition *only* through the standard AWS SDK (boto3),
exactly like an app built on Amazon Rekognition. The single difference is the
``REKOGNITION_ENDPOINT`` setting:

    REKOGNITION_ENDPOINT=https://facegate.internal:8000   -> self-hosted FaceGate
    REKOGNITION_ENDPOINT unset                            -> real Amazon Rekognition

Workflow (as in the brief):
  1. the iPad/iPhone kiosk detects a face on-device and captures a selfie;
  2. this backend calls SearchFacesByImage; a match marks attendance,
     no match (or a spoof / ambiguous decision) rejects.

Run:  python -m demo.attendance_backend   (see README for HTTPS on iPad)
"""

from __future__ import annotations

import base64
import contextvars
import hmac
import mimetypes
import os
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# Windows' MIME registry often lacks these; browsers refuse ES modules and
# streaming WebAssembly served as text/plain.
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")

HERE = Path(__file__).parent
STATIC = HERE / "static"

ENDPOINT = os.environ.get("REKOGNITION_ENDPOINT", "http://127.0.0.1:8000")
REGION = os.environ.get("AWS_REGION", "us-east-1")
COLLECTION = os.environ.get("ATTENDANCE_COLLECTION", "employees")
# Typical values used by Rekognition attendance apps.
MATCH_THRESHOLD = float(os.environ.get("FACE_MATCH_THRESHOLD", "95"))
LIVENESS_MIN_CONFIDENCE = float(os.environ.get("LIVENESS_MIN_CONFIDENCE", "70"))
DB_PATH = Path(os.environ.get("ATTENDANCE_DB", HERE.parent / "data" / "demo" / "attendance.db"))

rekognition = boto3.client(
    "rekognition",
    endpoint_url=ENDPOINT or None,
    region_name=REGION,
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "AKIAFACEGATEDEMO0001"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "demo-secret-change-me"),
    config=Config(retries={"max_attempts": 2}, tcp_keepalive=True, max_pool_connections=20),
    verify=os.environ.get("REKOGNITION_VERIFY_TLS", "true").lower() != "false",
)

_db_lock = threading.Lock()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_db = sqlite3.connect(str(DB_PATH), check_same_thread=False, isolation_level=None)
_db.row_factory = sqlite3.Row
_db.executescript(
    """
    CREATE TABLE IF NOT EXISTS employees (employee_id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, employee_id TEXT, name TEXT,
        result TEXT NOT NULL, similarity REAL, liveness TEXT, decision TEXT,
        server_ms REAL, roundtrip_ms REAL, mode TEXT
    );
    """
)
# Pilot-test labels (added later; migrate older demo databases in place).
_cols = {r[1] for r in _db.execute("PRAGMA table_info(attendance)")}
for _col in ("test_label", "participant", "attempt_id"):
    if _col not in _cols:
        _db.execute(f"ALTER TABLE attendance ADD COLUMN {_col} TEXT")

# Set per request by the kiosk's pilot mode: what this attempt is (genuine or
# an attack type) and who it targets, so eval/pilot_report.py can score it.
_test_label: contextvars.ContextVar[str | None] = contextvars.ContextVar("test_label", default=None)
_participant: contextvars.ContextVar[str | None] = contextvars.ContextVar("participant", default=None)
# Groups an automatic retry with the attempt it belongs to.
_attempt: contextvars.ContextVar[str | None] = contextvars.ContextVar("attempt", default=None)


def _set_pilot_labels(label: str | None, participant: str | None, attempt: str | None = None) -> None:
    _test_label.set((label or "").strip()[:40] or None)
    _participant.set((participant or "").strip()[:40] or None)
    _attempt.set((attempt or "").strip()[:64] or None)


def _q(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    with _db_lock:
        return _db.execute(sql, args).fetchall()


def _ensure_collection() -> None:
    try:
        rekognition.create_collection(CollectionId=COLLECTION)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise


def _b64image(data: str) -> bytes:
    if "," in data[:64]:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_collection()
    yield


app = FastAPI(title="Attendance demo", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# Shared password for when the demo is reachable from the internet (e.g. via a
# tunnel). Browsers ask once and then send it with every request, including
# the kiosk's own API calls. Any username is accepted.
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")


@app.middleware("http")
async def require_password(request: Request, call_next):
    if DEMO_PASSWORD:
        ok = False
        auth = request.headers.get("authorization", "")
        if auth.startswith("Basic "):
            try:
                _, _, pw = base64.b64decode(auth[6:]).decode().partition(":")
                ok = hmac.compare_digest(pw, DEMO_PASSWORD)
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="FaceGate demo"'})
    response = await call_next(request)
    # The kiosk's own pages and scripts change between test rounds: make every
    # browser revalidate them, or a phone can run a stale face.js against a new
    # kiosk.html and break. (The large MediaPipe files may stay cached.)
    if not request.url.path.startswith("/static/vendor/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def kiosk():
    return FileResponse(STATIC / "kiosk.html")


@app.get("/enroll")
def enroll_page():
    return FileResponse(STATIC / "enroll.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(STATIC / "dashboard.html")


# --- Liveness REST API tester (/v1/liveness on a deployed FaceGate) ---------
# The API key stays here on the backend, exactly as an integrating app should
# keep it; the browser only ever sees the session id and the capture page.
LIVENESS_API_URL = os.environ.get("LIVENESS_API_URL", "").rstrip("/")
LIVENESS_API_KEY = os.environ.get("LIVENESS_API_KEY", "")


@app.get("/liveness-test")
def liveness_test_page():
    return FileResponse(STATIC / "liveness_test.html")


def _liveness_api(method: str, path: str, **kw) -> JSONResponse:
    if not LIVENESS_API_URL or not LIVENESS_API_KEY:
        return JSONResponse({"error": {"message": "Set LIVENESS_API_URL and LIVENESS_API_KEY to use the liveness tester."}}, status_code=503)
    r = httpx.request(method, f"{LIVENESS_API_URL}{path}", headers={"x-api-key": LIVENESS_API_KEY}, timeout=30, **kw)
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/liveness-test/start")
def liveness_test_start():
    return _liveness_api("POST", "/v1/liveness/sessions", json={"clientReference": "demo-liveness-test"})


@app.get("/api/liveness-test/{session_id}/result")
def liveness_test_result(session_id: str):
    return _liveness_api("GET", f"/v1/liveness/sessions/{session_id}/result", params={"includeReferenceImage": "true"})


@app.post("/api/enroll")
async def enroll(request: Request):
    body = await request.json()
    emp_id = str(body.get("employee_id", "")).strip()
    name = str(body.get("name", "")).strip() or emp_id
    images = body.get("images") or ([body["image"]] if body.get("image") else [])
    if not emp_id or not images:
        raise HTTPException(400, "employee_id and image(s) are required")
    results = []
    for img in images:
        try:
            r = rekognition.index_faces(
                CollectionId=COLLECTION,
                Image={"Bytes": _b64image(img)},
                ExternalImageId=emp_id,
                MaxFaces=1,
                QualityFilter="AUTO",
                DetectionAttributes=["DEFAULT"],
            )
        except ClientError as e:
            raise HTTPException(400, e.response["Error"]["Message"]) from e
        hdr = r["ResponseMetadata"]["HTTPHeaders"]
        results.append(
            {
                "indexed": len(r["FaceRecords"]),
                "face_id": r["FaceRecords"][0]["Face"]["FaceId"] if r["FaceRecords"] else None,
                "unindexed_reasons": [u["Reasons"] for u in r.get("UnindexedFaces", [])],
                "lookalike_warning": hdr.get("x-facegate-lookalike"),
                "liveness": hdr.get("x-facegate-liveness"),
            }
        )
    if any(r["indexed"] for r in results):
        _q("INSERT OR REPLACE INTO employees VALUES (?,?,?)", (emp_id, name, time.time()))
    return {"employee_id": emp_id, "name": name, "results": results}


@app.get("/api/employees")
def employees():
    faces = {}
    token = None
    while True:
        kw = {"CollectionId": COLLECTION, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        r = rekognition.list_faces(**kw)
        for f in r["Faces"]:
            faces.setdefault(f.get("ExternalImageId"), []).append(f["FaceId"])
        token = r.get("NextToken")
        if not token:
            break
    rows = _q("SELECT * FROM employees ORDER BY created_at DESC")
    return [{"employee_id": r["employee_id"], "name": r["name"], "faces": len(faces.get(r["employee_id"], []))} for r in rows]


@app.delete("/api/employees/{employee_id}")
def delete_employee(employee_id: str):
    r = rekognition.list_faces(CollectionId=COLLECTION, MaxResults=4096)
    ids = [f["FaceId"] for f in r["Faces"] if f.get("ExternalImageId") == employee_id]
    if ids:
        rekognition.delete_faces(CollectionId=COLLECTION, FaceIds=ids)
    _q("DELETE FROM employees WHERE employee_id=?", (employee_id,))
    return {"deleted_faces": len(ids)}


def _record(result: str, emp: str | None, similarity: float | None, liveness: str | None, decision: str | None, server_ms: float | None, rt_ms: float, mode: str) -> dict:
    name = None
    if emp:
        row = _q("SELECT name FROM employees WHERE employee_id=?", (emp,))
        name = row[0]["name"] if row else emp
    _q(
        "INSERT INTO attendance (ts, employee_id, name, result, similarity, liveness, decision, server_ms, roundtrip_ms, mode, test_label, participant, attempt_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (time.time(), emp, name, result, similarity, liveness, decision, server_ms, rt_ms, mode, _test_label.get(), _participant.get(), _attempt.get()),
    )
    return {
        "result": result,
        "employee_id": emp,
        "name": name,
        "similarity": similarity,
        "liveness": liveness,
        "decision": decision,
        "server_ms": server_ms,
        "backend_to_face_service_ms": round(rt_ms, 1),
        "time": datetime.now().strftime("%H:%M:%S"),
    }


def _search(image: bytes, mode: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = rekognition.search_faces_by_image(
            CollectionId=COLLECTION, Image={"Bytes": image}, MaxFaces=1, FaceMatchThreshold=MATCH_THRESHOLD
        )
    except rekognition.exceptions.InvalidParameterException:
        return _record("no_face", None, None, None, None, None, (time.perf_counter() - t0) * 1000, mode)
    rt = (time.perf_counter() - t0) * 1000
    hdr = r["ResponseMetadata"]["HTTPHeaders"]
    server_ms = float(hdr["x-facegate-server-ms"]) if "x-facegate-server-ms" in hdr else None
    decision = hdr.get("x-facegate-decision")
    liveness = hdr.get("x-facegate-liveness")
    if r["FaceMatches"]:
        m = r["FaceMatches"][0]
        return _record("present", m["Face"].get("ExternalImageId"), round(m["Similarity"], 3), liveness, decision, server_ms, rt, mode)
    result = "spoof" if decision == "spoof" else "ambiguous" if (decision or "").startswith("ambiguous") else "unknown"
    return _record(result, None, None, liveness, decision, server_ms, rt, mode)


@app.post("/api/checkin")
async def checkin(request: Request):
    """Fast path: one selfie -> SearchFacesByImage (passive liveness on server)."""
    body = await request.json()
    _set_pilot_labels(body.get("test_label"), body.get("participant"), body.get("attempt_id"))
    return _search(_b64image(body["image"]), "passive")


# --- Secure path: Rekognition-style liveness session ------------------------
@app.post("/api/liveness/start")
def liveness_start():
    sid = rekognition.create_face_liveness_session(Settings={"AuditImagesLimit": 0})["SessionId"]
    r = httpx.get(f"{ENDPOINT}/liveness/sessions/{sid}/challenge", verify=False, timeout=10)
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/liveness/{session_id}/frames")
async def liveness_frames(session_id: str, request: Request):
    # Proxied so the kiosk only has to trust one HTTPS origin. In production
    # the device can post straight to FaceGate (CORS is enabled there).
    q = request.query_params
    _set_pilot_labels(q.get("test_label"), q.get("participant"), q.get("attempt_id"))
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        r = await client.post(f"{ENDPOINT}/liveness/sessions/{session_id}/frames", content=await request.body(), headers={"content-type": "application/json"})
    if r.status_code != 200:
        return JSONResponse(r.json(), status_code=r.status_code)
    res = rekognition.get_face_liveness_session_results(SessionId=session_id)
    conf = res.get("Confidence", 0.0)
    hdr = res["ResponseMetadata"]["HTTPHeaders"]
    reasons = hdr.get("x-facegate-liveness-reasons", "")
    # Retry guidance: Rekognition's Feedback codes plus FaceGate's extras.
    feedback = [c for c in hdr.get("x-facegate-liveness-feedback", "").split(",") if c]
    if not feedback:
        feedback = [f["Code"] for f in res.get("Feedback", [])]
    if res["Status"] != "SUCCEEDED" or conf < LIVENESS_MIN_CONFIDENCE:
        out = _record("spoof", None, None, f"session_confidence={conf:.1f};reasons={reasons};feedback={','.join(feedback)}", "liveness_failed", None, 0.0, "session")
        out["liveness_confidence"] = conf
        out["feedback"] = feedback
        return out
    out = _search(res["ReferenceImage"]["Bytes"], "session")
    out["liveness_confidence"] = conf
    return out


@app.post("/api/detect")
async def detect(request: Request):
    """Fallback face detection for devices that cannot run MediaPipe."""
    body = await request.json()
    try:
        r = rekognition.detect_faces(Image={"Bytes": _b64image(body["image"])})
    except ClientError:
        return []
    return [d["BoundingBox"] | {"Confidence": d["Confidence"]} for d in r["FaceDetails"]]


@app.get("/api/attendance")
def attendance(limit: int = 50):
    rows = _q("SELECT * FROM attendance ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) | {"time": datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S")} for r in rows]


@app.get("/api/config")
def config():
    return {
        "endpoint": ENDPOINT or "Amazon Rekognition (AWS)",
        "collection": COLLECTION,
        "match_threshold": MATCH_THRESHOLD,
        "liveness_min_confidence": LIVENESS_MIN_CONFIDENCE,
    }


def main() -> None:
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--ssl-certfile")
    ap.add_argument("--ssl-keyfile")
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, ssl_certfile=a.ssl_certfile, ssl_keyfile=a.ssl_keyfile)


if __name__ == "__main__":
    main()

