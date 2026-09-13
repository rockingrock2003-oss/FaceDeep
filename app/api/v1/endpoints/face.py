import json
import uuid

import cv2
import numpy as np
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.models.import_job import ImportJob
from app.schemas.face import (
    BulkEnrollItem,
    BulkEnrollResponse,
    BulkImportRequest,
    FaceDeleteRequest,
    FaceEnrollResponse,
    FaceMatchResponse,
    FaceRecognizeResponse,
    ImportJobResponse,
    ImportJobStatusResponse,
)
from app.services.embedding_store import EmbeddingStore
from app.services.face_recognition import get_face_service
from app.services.import_worker import process_import_job
from app.services.liveness import LivenessDetector
from app.services.tier_service import tier_enforcement

router = APIRouter(prefix="/face", tags=["Face Recognition"])

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

embedding_store = EmbeddingStore()
liveness_detector = LivenessDetector()


def validate_image_dimensions(image_bytes: bytes) -> np.ndarray:
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file",
        )
    return img


async def validate_api_key(
    api_key: str = Depends(API_KEY_HEADER),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, AsyncSession]:
    return current_user, db


@router.post("/enroll", response_model=FaceEnrollResponse, status_code=status.HTTP_201_CREATED)
async def enroll_face(
    file: UploadFile = File(...),
    person_id: str = Form(...),
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG)",
        )

    if not person_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="person_id is required",
        )

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size must be less than 10MB",
        )

    validate_image_dimensions(image_bytes)

    face_service = get_face_service()
    try:
        embedding, face_info = await face_service.extract_embedding(image_bytes)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    face_id = str(uuid.uuid4())
    result = embedding_store.add_embedding(
        user_id=current_user.id,
        face_id=face_id,
        embedding=embedding,
        person_id=person_id,
    )

    current_user.entry_in_chroma_db += 1
    current_user.add_count += 1
    await db.commit()

    message = "Face enrolled successfully"
    if result["removed_count"] > 0:
        message += f". Removed {result['removed_count']} oldest embedding(s)"

    return FaceEnrollResponse(
        status="success",
        face_id=result["face_id"],
        person_id=person_id,
        message=message,
        removed_count=result["removed_count"] if result["removed_count"] > 0 else None,
        removed_uploaded_times=(
            result["removed_uploaded_times"]
            if result["removed_count"] > 0
            else None
        ),
    )


@router.post("/recognize", response_model=FaceRecognizeResponse)
async def recognize_face(
    file: UploadFile = File(...),
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth
    await tier_enforcement.enforce_or_raise(db, current_user)

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG)",
        )

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size must be less than 10MB",
        )

    validate_image_dimensions(image_bytes)

    liveness_result = await liveness_detector.check_liveness(image_bytes)
    if liveness_result["status"] != "passed":
        tier_enforcement.increment_usage(current_user)
        await db.commit()
        return FaceRecognizeResponse(
            status="not_live",
            person_id=-1,
            confidence=None,
            message=liveness_result["message"],
            liveness=liveness_result["components"],
        )

    face_service = get_face_service()
    try:
        embedding, face_info = await face_service.extract_embedding(image_bytes)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    matches = embedding_store.search(
        user_id=current_user.id,
        query_embedding=embedding,
        n_results=1,
    )

    tier_enforcement.increment_usage(current_user)
    await db.commit()

    if not matches:
        return FaceRecognizeResponse(
            status="not_found",
            person_id=-1,
            confidence=None,
            message="No matching face found in database",
            liveness=liveness_result["components"],
        )

    best_match = matches[0]
    if best_match["similarity"] >= settings.FACE_RECOGNITION_THRESHOLD:
        return FaceRecognizeResponse(
            status="found",
            person_id=best_match["person_id"],
            confidence=round(best_match["similarity"], 4),
            message=f"Face recognized as {best_match['person_id']}",
            liveness=liveness_result["components"],
        )

    return FaceRecognizeResponse(
        status="not_found",
        person_id=-1,
        confidence=round(best_match["similarity"], 4),
        message="No matching face found above threshold",
        liveness=liveness_result["components"],
    )


@router.post("/ismatch", response_model=FaceMatchResponse)
async def is_match(
    file: UploadFile = File(...),
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth
    await tier_enforcement.enforce_or_raise(db, current_user)

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG)",
        )

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size must be less than 10MB",
        )

    validate_image_dimensions(image_bytes)

    face_service = get_face_service()

    try:
        embedding, _ = await face_service.extract_embedding(image_bytes)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    matches = embedding_store.search(
        user_id=current_user.id,
        query_embedding=embedding,
        n_results=1,
    )

    tier_enforcement.increment_usage(current_user)
    await db.commit()

    if not matches:
        return FaceMatchResponse(
            status="no_match",
            is_match=False,
            person_id=None,
            confidence=None,
            message="No matching face found in database",
        )

    best_match = matches[0]
    if best_match["similarity"] >= settings.FACE_RECOGNITION_THRESHOLD:
        return FaceMatchResponse(
            status="match",
            is_match=True,
            person_id=best_match["person_id"],
            confidence=round(best_match["similarity"], 4),
            message=f"Face matches person_id: {best_match['person_id']}",
        )

    return FaceMatchResponse(
        status="no_match",
        is_match=False,
        person_id=None,
        confidence=round(best_match["similarity"], 4),
        message="No matching face found above threshold",
    )


@router.put("/update", response_model=FaceEnrollResponse)
async def update_face(
    file: UploadFile = File(...),
    person_id: str = Form(...),
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG)",
        )

    if not person_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="person_id is required",
        )

    face_ids_to_update = embedding_store.get_face_ids_by_person_id(
        user_id=current_user.id,
        person_id=person_id,
    )

    if not face_ids_to_update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"person_id '{person_id}' not found",
        )

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size must be less than 10MB",
        )

    validate_image_dimensions(image_bytes)

    face_service = get_face_service()
    try:
        embedding, face_info = await face_service.extract_embedding(image_bytes)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    for face_id in face_ids_to_update:
        embedding_store.update_embedding(
            user_id=current_user.id,
            face_id=face_id,
            embedding=embedding,
            person_id=person_id,
        )

    current_user.update_count += 1
    await db.commit()

    return FaceEnrollResponse(
        status="success",
        face_id=face_ids_to_update[0] if face_ids_to_update else "new",
        person_id=person_id,
        message=f"Updated {len(face_ids_to_update)} embedding(s) for person_id '{person_id}'",
    )


@router.delete("/delete")
async def delete_face(
    body: FaceDeleteRequest,
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth
    deleted_count = embedding_store.delete_by_person_id(
        user_id=current_user.id,
        person_id=body.person_id,
    )

    if deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"person_id '{body.person_id}' not found",
        )

    current_user.delete_count += deleted_count
    current_user.entry_in_chroma_db = max(0, current_user.entry_in_chroma_db - deleted_count)
    await db.commit()

    return {
        "status": "success",
        "person_id": body.person_id,
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} embedding(s) for person_id '{body.person_id}'",
    }


@router.get("/persons")
async def list_persons(auth: tuple = Depends(validate_api_key)):
    current_user, db = auth
    persons = embedding_store.list_persons(current_user.id)
    return {
        "status": "success",
        "count": len(persons),
        "persons": persons,
    }


@router.post("/bulk-enroll", response_model=BulkEnrollResponse)
async def bulk_enroll_faces(
    files: list[UploadFile] = File(...),
    person_id: str = Form(...),
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth

    if not person_id:
        raise HTTPException(status_code=400, detail="person_id is required")

    face_service = get_face_service()
    results = []
    success_count = 0
    failed_count = 0

    for file in files:
        face_id = str(uuid.uuid4())
        try:
            if not file.content_type or not file.content_type.startswith("image/"):
                results.append(
                    BulkEnrollItem(face_id=face_id, status="failed", message="Not an image")
                )
                failed_count += 1
                continue

            image_bytes = await file.read()
            if len(image_bytes) > 10 * 1024 * 1024:
                results.append(
                    BulkEnrollItem(face_id=face_id, status="failed", message="File too large")
                )
                failed_count += 1
                continue

            img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                results.append(
                    BulkEnrollItem(face_id=face_id, status="failed", message="Invalid image")
                )
                failed_count += 1
                continue

            embedding, face_info = await face_service.extract_embedding(image_bytes)

            embedding_store.add_embedding(
                user_id=current_user.id,
                face_id=face_id,
                embedding=embedding,
                person_id=person_id,
            )

            current_user.entry_in_chroma_db += 1
            current_user.add_count += 1
            success_count += 1
            results.append(BulkEnrollItem(face_id=face_id, status="success", message="Enrolled"))

        except Exception as e:
            failed_count += 1
            results.append(BulkEnrollItem(face_id=face_id, status="failed", message=str(e)))

    await db.commit()

    return BulkEnrollResponse(
        status="completed",
        total=len(files),
        success=success_count,
        failed=failed_count,
        results=results,
    )


@router.post("/bulk-import", response_model=ImportJobResponse)
async def bulk_import_from_urls(
    body: BulkImportRequest,
    background_tasks: BackgroundTasks,
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth

    if not body.person_id:
        raise HTTPException(status_code=400, detail="person_id is required")
    if not body.image_urls:
        raise HTTPException(status_code=400, detail="image_urls is required")

    job = ImportJob(
        user_id=current_user.id,
        person_id=body.person_id,
        total=len(body.image_urls),
        status="queued",
    )
    db.add(job)
    await db.flush()
    await db.commit()

    background_tasks.add_task(
        process_import_job,
        job_id=job.id,
        user_id=current_user.id,
        person_id=body.person_id,
        image_urls=body.image_urls,
    )

    return ImportJobResponse(
        job_id=job.id,
        status="queued",
        message=f"Import started. {len(body.image_urls)} images queued for processing.",
    )


@router.get("/import-status/{job_id}", response_model=ImportJobStatusResponse)
async def get_import_status(
    job_id: str,
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth

    stmt = select(ImportJob).where(
        ImportJob.id == job_id,
        ImportJob.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    progress = (job.processed / job.total * 100) if job.total > 0 else 0
    errors = json.loads(job.errors) if job.errors else None

    return ImportJobStatusResponse(
        job_id=job.id,
        status=job.status,
        total=job.total,
        processed=job.processed,
        success=job.success,
        failed=job.failed,
        progress_percent=round(progress, 1),
        errors=errors,
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.get("/import-jobs")
async def list_import_jobs(
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth

    stmt = (
        select(ImportJob)
        .where(ImportJob.user_id == current_user.id)
        .order_by(ImportJob.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    jobs = result.scalars().all()

    return {
        "status": "success",
        "count": len(jobs),
        "jobs": [
            {
                "job_id": job.id,
                "person_id": job.person_id,
                "status": job.status,
                "total": job.total,
                "processed": job.processed,
                "success": job.success,
                "failed": job.failed,
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
            for job in jobs
        ],
    }


@router.delete("/clear")
async def clear_all_faces(
    auth: tuple = Depends(validate_api_key),
):
    current_user, db = auth
    deleted_count = embedding_store.clear_all_embeddings(current_user.id)

    return {
        "status": "success",
        "message": f"Cleared {deleted_count} embeddings",
        "deleted_count": deleted_count,
    }
