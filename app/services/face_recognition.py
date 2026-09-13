import asyncio
from functools import lru_cache

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.core.config import settings

REQUIRED_EMBEDDING_DIM = 512


class FaceRecognitionService:
    def __init__(self):
        self.app = FaceAnalysis(
            providers=["CPUExecutionProvider"],
            name=settings.ARCFACE_MODEL_PATH,
        )
        self.app.prepare(ctx_id=-1, det_size=(settings.ARCFACE_DET_SIZE, settings.ARCFACE_DET_SIZE))
        self.threshold = settings.FACE_RECOGNITION_THRESHOLD

    def _decode_image(self, image_bytes: bytes) -> np.ndarray:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image")
        return img

    def _normalize_embedding(self, embedding: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(embedding)
        if norm == 0:
            raise ValueError("Zero-norm embedding")
        return (embedding / norm).astype(np.float32)

    def extract_embedding_sync(self, image_bytes: bytes) -> tuple[np.ndarray, dict]:
        img = self._decode_image(image_bytes)
        faces = self.app.get(img)

        if not faces:
            raise ValueError("No face detected in the image")

        best_face = max(faces, key=lambda f: f.det_score)
        embedding = best_face.embedding

        if embedding.shape[0] != REQUIRED_EMBEDDING_DIM:
            raise ValueError(
                f"Expected {REQUIRED_EMBEDDING_DIM} dimensions, got {embedding.shape[0]}"
            )

        embedding = self._normalize_embedding(embedding)

        return embedding, {
            "bbox": best_face.bbox.tolist(),
            "det_score": float(best_face.det_score),
            "landmarks": best_face.kps.tolist() if hasattr(best_face, "kps") else None,
        }

    async def extract_embedding(self, image_bytes: bytes) -> tuple[np.ndarray, dict]:
        return await asyncio.to_thread(self.extract_embedding_sync, image_bytes)

    def compare_embeddings(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(emb1, emb2) / (norm1 * norm2))


@lru_cache
def get_face_service() -> FaceRecognitionService:
    return FaceRecognitionService()
