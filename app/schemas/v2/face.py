from pydantic import BaseModel, Field


class FaceEnrollRequest(BaseModel):
    person_id: str
    metadata: dict | None = Field(default=None, description="Optional metadata for the face")


class FaceEnrollResponse(BaseModel):
    status: str
    face_id: str
    person_id: str
    message: str
    removed_count: int | None = None
    removed_uploaded_times: list[str] | None = None
    processing_time_ms: float | None = None
    model_version: str | None = None
    embedding_dimensions: int | None = None


class LivenessInfo(BaseModel):
    score: float | None = None
    label: str | None = None
    components: dict | None = None


class FaceRecognizeResponse(BaseModel):
    status: str
    person_id: str | int
    confidence: float | None = None
    similarity: float | None = None
    message: str
    liveness: LivenessInfo | None = None
    processing_time_ms: float | None = None
    model_version: str | None = None
    threshold: float | None = None


class FaceMatchResponse(BaseModel):
    status: str
    is_match: bool
    person_id: str | None = None
    confidence: float | None = None
    similarity: float | None = None
    message: str
    processing_time_ms: float | None = None


class FaceDeleteRequest(BaseModel):
    person_id: str


class BulkEnrollItem(BaseModel):
    face_id: str
    status: str
    message: str


class BulkEnrollResponse(BaseModel):
    status: str
    total: int
    success: int
    failed: int
    results: list[BulkEnrollItem]
    processing_time_ms: float | None = None


class BulkImportRequest(BaseModel):
    person_id: str
    image_urls: list[str]
    metadata: dict | None = Field(default=None, description="Optional metadata for all imported faces")


class ImportJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    total: int | None = None


class ImportJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total: int
    processed: int
    success: int
    failed: int
    progress_percent: float
    errors: list[str] | None = None
    created_at: str
    completed_at: str | None = None
    processing_time_ms: float | None = None


class PaginatedPersonsResponse(BaseModel):
    status: str
    count: int
    persons: list[dict]
    has_more: bool = False


class ClearAllResponse(BaseModel):
    status: str
    message: str
    deleted_count: int
    person_count: int
