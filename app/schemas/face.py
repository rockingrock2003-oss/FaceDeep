from pydantic import BaseModel


class FaceEnrollRequest(BaseModel):
    person_id: str


class FaceEnrollResponse(BaseModel):
    status: str
    face_id: str
    person_id: str
    message: str
    removed_count: int | None = None
    removed_uploaded_times: list[str] | None = None


class FaceRecognizeResponse(BaseModel):
    status: str
    person_id: str | int
    confidence: float | None = None
    message: str
    liveness: dict | None = None


class FaceMatchResponse(BaseModel):
    status: str
    is_match: bool
    person_id: str | None = None
    confidence: float | None = None
    message: str


class FaceDeleteRequest(BaseModel):
    person_id: str


class FaceUpdateRequest(BaseModel):
    person_id: str


class FaceSearchResult(BaseModel):
    face_id: str
    person_id: str
    similarity: float


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


class BulkImportRequest(BaseModel):
    person_id: str
    image_urls: list[str]


class ImportJobResponse(BaseModel):
    job_id: str
    status: str
    message: str


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
