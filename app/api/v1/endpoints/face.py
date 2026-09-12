import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.core.security import get_current_user
from app.models import User
from app.schemas.face import (
    FaceDeleteRequest,
    FaceEnrollResponse,
    FaceRecognizeResponse,
    FaceSearchResult,
    FaceUpdateRequest,
    LivenessResponse,
)
from app.services.embedding_store import EmbeddingStore
from app.services.face_recognition import get_face_service
from app.services.liveness import LivenessDetector

router = APIRouter(prefix="/face", tags=["Face Recognition"])

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

embedding_store = EmbeddingStore()
liveness_detector = LivenessDetector()


async def validate_api_key(
    api_key: str = Depends(API_KEY_HEADER),
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.post("/liveness", response_model=LivenessResponse)
async def check_liveness(
    file: UploadFile = File(...),
    current_user: User = Depends(validate_api_key),
):
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

    result = await liveness_detector.check_liveness(image_bytes)

    return LivenessResponse(
        status=result["status"],
        liveness_score=result["liveness_score"],
        label=result["label"],
        message=result["message"],
        components=result.get("components"),
    )


@router.post("/enroll", response_model=FaceEnrollResponse, status_code=status.HTTP_201_CREATED)
async def enroll_face(
    file: UploadFile = File(...),
    person_id: str = "",
    label: str = "",
    current_user: User = Depends(validate_api_key),
):
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

    if not label:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="label is required",
        )

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size must be less than 10MB",
        )

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
        label=label,
    )

    return FaceEnrollResponse(
        status="success",
        face_id=result["face_id"],
        person_id=result["person_id"],
        label=result["label"],
        message="Face enrolled successfully",
    )


@router.post("/recognize", response_model=FaceRecognizeResponse)
async def recognize_face(
    file: UploadFile = File(...),
    check_liveness_first: bool = True,
    current_user: User = Depends(validate_api_key),
):
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

    if check_liveness_first:
        liveness_result = await liveness_detector.check_liveness(image_bytes)
        if liveness_result["status"] != "passed":
            return FaceRecognizeResponse(
                status="not_live",
                person_id=-1,
                confidence=None,
                message=liveness_result["message"],
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

    if not matches:
        return FaceRecognizeResponse(
            status="not_found",
            person_id=-1,
            confidence=None,
            message="No matching face found in database",
        )

    best_match = matches[0]
    if best_match["similarity"] >= settings.FACE_RECOGNITION_THRESHOLD:
        return FaceRecognizeResponse(
            status="found",
            person_id=best_match["person_id"],
            confidence=round(best_match["similarity"], 4),
            message=f"Face recognized as {best_match['label']}",
        )

    return FaceRecognizeResponse(
        status="not_found",
        person_id=-1,
        confidence=round(best_match["similarity"], 4),
        message="No matching face found above threshold",
    )


@router.put("/update", response_model=FaceEnrollResponse)
async def update_face(
    file: UploadFile = File(...),
    person_id: str = "",
    label: str = "",
    current_user: User = Depends(validate_api_key),
):
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
            label=label or person_id,
        )

    return FaceEnrollResponse(
        status="success",
        face_id=face_ids_to_update[0] if face_ids_to_update else "new",
        person_id=person_id,
        label=label or person_id,
        message=f"Updated {len(face_ids_to_update)} embedding(s) for person_id '{person_id}'",
    )


@router.delete("/delete")
async def delete_face(
    body: FaceDeleteRequest,
    current_user: User = Depends(validate_api_key),
):
    deleted_count = embedding_store.delete_by_person_id(
        user_id=current_user.id,
        person_id=body.person_id,
    )

    if deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"person_id '{body.person_id}' not found",
        )

    return {
        "status": "success",
        "person_id": body.person_id,
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} embedding(s) for person_id '{body.person_id}'",
    }


@router.get("/persons")
async def list_persons(current_user: User = Depends(validate_api_key)):
    persons = embedding_store.list_persons(current_user.id)
    return {
        "status": "success",
        "count": len(persons),
        "persons": persons,
    }
