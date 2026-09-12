from pydantic import BaseModel


class FaceEnrollRequest(BaseModel):
    person_id: str
    label: str


class FaceEnrollResponse(BaseModel):
    status: str
    face_id: str
    person_id: str
    label: str
    message: str


class FaceRecognizeResponse(BaseModel):
    status: str
    person_id: str | int
    confidence: float | None = None
    message: str


class LivenessResponse(BaseModel):
    status: str
    liveness_score: float
    label: str
    message: str
    components: dict | None = None


class FaceDeleteRequest(BaseModel):
    person_id: str


class FaceUpdateRequest(BaseModel):
    person_id: str
    label: str


class FaceSearchResult(BaseModel):
    face_id: str
    person_id: str
    label: str
    similarity: float
