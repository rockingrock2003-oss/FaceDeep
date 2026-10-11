import hashlib
import io
import json
import logging
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.core.security import get_current_user
from app.models import User
from app.services.image_processor import (
    MAX_RESOLUTION,
    SUPPORTED_FORMATS,
    validate_image,
)

logger = logging.getLogger("facedeep.upload")

router = APIRouter(prefix="/upload", tags=["Image Upload"])

CHUNK_SIZE = 5 * 1024 * 1024
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
UPLOAD_ROOT = Path(tempfile.gettempdir()) / "facedeep_uploads"

_upload_sessions: dict[str, dict] = {}


def _get_session(upload_id: str, current_user: User) -> dict:
    session = _upload_sessions.get(upload_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return session


def _cleanup_session_files(session: dict) -> None:
    session_dir = session.get("session_dir")
    if session_dir:
        shutil.rmtree(session_dir, ignore_errors=True)


@router.post("/presigned-url")
async def generate_presigned_upload(
    filename: str,
    content_type: str,
    file_size: int,
    current_user: User = Depends(get_current_user),
):
    if content_type not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {content_type}")
    if file_size <= 0:
        raise HTTPException(status_code=400, detail="File size must be greater than zero")
    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    safe_filename = Path(filename).name
    if not safe_filename or safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    upload_id = str(uuid.uuid4())
    session_dir = UPLOAD_ROOT / current_user.id / upload_id
    session_dir.mkdir(parents=True, exist_ok=False)
    total_chunks = max(1, (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE)
    key = f"uploads/{current_user.id}/{upload_id}/{safe_filename}"

    _upload_sessions[upload_id] = {
        "user_id": current_user.id,
        "key": key,
        "filename": safe_filename,
        "content_type": content_type,
        "file_size": file_size,
        "total_chunks": total_chunks,
        "parts": {},
        "status": "pending",
        "created_at": time.time(),
        "session_dir": str(session_dir),
        "completed_path": None,
    }

    return {
        "upload_id": upload_id,
        "presigned_url": f"/api/v2/upload/{upload_id}/part",
        "key": key,
        "chunk_size": CHUNK_SIZE,
        "total_chunks": total_chunks,
    }


@router.post("/{upload_id}/part")
async def upload_part(
    upload_id: str,
    part_number: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    session = _get_session(upload_id, current_user)
    if session["status"] != "pending":
        raise HTTPException(status_code=409, detail="Upload is already completed")

    if part_number < 1 or part_number > session["total_chunks"]:
        raise HTTPException(
            status_code=400,
            detail=f"Part number must be between 1 and {session['total_chunks']}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Upload part is empty")
    if len(data) > CHUNK_SIZE:
        raise HTTPException(status_code=413, detail="Upload part exceeds chunk size")

    old_part = session["parts"].get(part_number)
    previous_size = old_part["size"] if old_part else 0
    uploaded_size = (
        sum(part["size"] for part in session["parts"].values()) - previous_size + len(data)
    )
    if uploaded_size > session["file_size"]:
        raise HTTPException(status_code=400, detail="Uploaded data exceeds declared file size")

    session_dir = Path(session["session_dir"])
    part_path = session_dir / f"part-{part_number:04d}"
    part_path.write_bytes(data)
    part_hash = hashlib.sha256(data).hexdigest()

    session["parts"][part_number] = {
        "part_number": part_number,
        "size": len(data),
        "hash": part_hash,
        "path": str(part_path),
    }

    return {
        "part_number": part_number,
        "hash": part_hash,
        "size": len(data),
        "parts_uploaded": len(session["parts"]),
    }


@router.post("/{upload_id}/complete")
async def complete_upload(
    upload_id: str,
    current_user: User = Depends(get_current_user),
):
    session = _get_session(upload_id, current_user)
    if session["status"] == "completed":
        return {
            "upload_id": upload_id,
            "status": "completed",
            "key": session["key"],
            "parts": len(session["parts"]),
            "total_size": session["file_size"],
            "download_url": f"/api/v2/upload/{upload_id}/file",
        }

    expected = set(range(1, session["total_chunks"] + 1))
    received = set(session["parts"])
    if received != expected:
        missing = sorted(expected - received)
        raise HTTPException(status_code=400, detail=f"Missing upload parts: {missing}")

    total_size = sum(part["size"] for part in session["parts"].values())
    if total_size != session["file_size"]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Uploaded size {total_size} does not match declared "
                f"file size {session['file_size']}"
            ),
        )

    completed_path = Path(session["session_dir"]) / session["filename"]
    with completed_path.open("wb") as output:
        for part_number in sorted(session["parts"]):
            part_path = Path(session["parts"][part_number]["path"])
            with part_path.open("rb") as part_file:
                shutil.copyfileobj(part_file, output)

    try:
        validate_image(completed_path.read_bytes())
    except Exception:
        completed_path.unlink(missing_ok=True)
        raise

    for part in session["parts"].values():
        Path(part["path"]).unlink(missing_ok=True)

    session["status"] = "completed"
    session["completed_path"] = str(completed_path)

    return {
        "upload_id": upload_id,
        "status": "completed",
        "key": session["key"],
        "parts": len(session["parts"]),
        "total_size": total_size,
        "download_url": f"/api/v2/upload/{upload_id}/file",
        "message": "Upload completed and validated.",
    }


@router.get("/{upload_id}/file")
async def download_uploaded_file(
    upload_id: str,
    current_user: User = Depends(get_current_user),
):
    session = _get_session(upload_id, current_user)
    path = session.get("completed_path")
    if session["status"] != "completed" or not path or not Path(path).is_file():
        raise HTTPException(status_code=409, detail="Upload is not completed")

    return FileResponse(
        path,
        media_type=session["content_type"],
        filename=session["filename"],
    )


@router.post("/process")
async def process_uploaded_image(
    file: UploadFile = File(...),
    target_format: str = Form(default="webp"),
    quality: int = Form(default=85),
    max_resolution: str = Form(default="4096x4096"),
    current_user: User = Depends(get_current_user),
):
    from app.services.image_processor import process_image

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await file.read()
    if len(image_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Image too large (max 10MB)")

    validate_image(image_bytes)

    try:
        width, height = max_resolution.lower().split("x", 1)
        res = (int(width), int(height))
        if res[0] <= 0 or res[1] <= 0:
            raise ValueError
    except ValueError:
        res = MAX_RESOLUTION

    try:
        processed, info = process_image(
            image_bytes,
            target_format=target_format,
            quality=quality,
            max_res=res,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(
        io.BytesIO(processed),
        media_type=f"image/{target_format}",
        headers={
            "X-Image-Info": json.dumps(info),
            "Content-Disposition": f'attachment; filename="processed.{target_format}"',
        },
    )


@router.delete("/{upload_id}")
async def abort_upload(
    upload_id: str,
    current_user: User = Depends(get_current_user),
):
    session = _get_session(upload_id, current_user)
    _upload_sessions.pop(upload_id, None)
    _cleanup_session_files(session)
    return {"status": "aborted", "upload_id": upload_id}
