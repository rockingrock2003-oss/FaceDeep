import hashlib
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.services.image_processor import (
    MAX_RESOLUTION,
    SUPPORTED_FORMATS,
    validate_image,
)

logger = logging.getLogger("facedeep.upload")

router = APIRouter(prefix="/upload", tags=["Image Upload"])

CHUNK_SIZE = 5 * 1024 * 1024  # 5MB chunks

_upload_sessions: dict[str, dict] = {}


@router.post("/presigned-url")
async def generate_presigned_upload(
    filename: str,
    content_type: str,
    file_size: int,
    current_user: User = Depends(get_current_user),
):
    if content_type not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {content_type}")

    if file_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    upload_id = str(uuid.uuid4())
    key = f"uploads/{current_user.id}/{upload_id}/{filename}"

    _upload_sessions[upload_id] = {
        "user_id": current_user.id,
        "key": key,
        "filename": filename,
        "content_type": content_type,
        "file_size": file_size,
        "parts": [],
        "status": "pending",
        "created_at": time.time(),
    }

    return {
        "upload_id": upload_id,
        "presigned_url": f"/api/v2/upload/{upload_id}/part",
        "key": key,
        "chunk_size": CHUNK_SIZE,
        "total_chunks": (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE if file_size > CHUNK_SIZE else 1,
    }


@router.post("/{upload_id}/part")
async def upload_part(
    upload_id: str,
    part_number: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    session = _upload_sessions.get(upload_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    data = await file.read()
    part_hash = hashlib.sha256(data).hexdigest()

    session["parts"].append({
        "part_number": part_number,
        "size": len(data),
        "hash": part_hash,
    })

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
    session = _upload_sessions.get(upload_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    session["status"] = "completed"

    return {
        "upload_id": upload_id,
        "status": "completed",
        "key": session["key"],
        "parts": len(session["parts"]),
        "total_size": sum(p["size"] for p in session["parts"]),
        "message": "Upload completed. Use /face/enroll with the uploaded file.",
    }


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
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 10MB)")

    validate_image(image_bytes)

    try:
        parts = max_resolution.split("x")
        res = (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        res = MAX_RESOLUTION

    try:
        processed, info = process_image(
            image_bytes,
            target_format=target_format,
            quality=quality,
            max_res=res,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    import io
    from fastapi.responses import StreamingResponse

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
    session = _upload_sessions.pop(upload_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    return {"status": "aborted", "upload_id": upload_id}
