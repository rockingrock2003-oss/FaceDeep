import asyncio
from functools import lru_cache

import cv2
import numpy as np

from app.core.config import settings


class LivenessDetector:
    def __init__(self):
        self.face_mesh = None
        self.min_score = settings.LIVENESS_MIN_SCORE
        self._mini_fasnet = None

    def _get_face_mesh(self):
        if self.face_mesh is None:
            import mediapipe as mp
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
            )
        return self.face_mesh

    def _get_mini_fasnet(self):
        if self._mini_fasnet is None:
            try:
                from app.services.mini_fasnet import get_mini_fasnet_ensemble
                self._mini_fasnet = get_mini_fasnet_ensemble()
            except Exception:
                pass
        return self._mini_fasnet

    def check_liveness_sync(self, image_bytes: bytes) -> dict:
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return {
                "status": "error",
                "liveness_score": 0,
                "label": "error",
                "message": "Could not decode image",
                "components": {},
            }

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        try:
            face_mesh = self._get_face_mesh()
        except (ImportError, AttributeError) as e:
            return {
                "status": "error",
                "liveness_score": 0,
                "label": "error",
                "message": f"MediaPipe not available: {e}",
                "components": {},
            }
        results = face_mesh.process(rgb)

        if not results.multi_face_landmarks:
            return {
                "status": "error",
                "liveness_score": 0,
                "label": "no_face",
                "message": "No face detected in the image",
                "components": {},
            }

        landmarks = results.multi_face_landmarks[0].landmark
        h, w = frame.shape[:2]

        mini_fasnet_detector = self._get_mini_fasnet()
        if not mini_fasnet_detector:
            return {
                "status": "error",
                "liveness_score": 0,
                "label": "error",
                "message": "Liveness model not available",
                "components": {},
            }

        mini_fasnet_result = mini_fasnet_detector.predict(frame, landmarks, w, h)

        if mini_fasnet_result["is_live"] is None:
            return {
                "status": "error",
                "liveness_score": 0,
                "label": "error",
                "message": mini_fasnet_result.get("error", "Liveness check failed"),
                "components": {},
            }

        live_prob = mini_fasnet_result["live_probability"]
        liveness_score = live_prob * 100

        if liveness_score >= self.min_score:
            label = "live"
            status = "passed"
            message = "Liveness check passed"
        elif liveness_score >= self.min_score * 0.5:
            label = "uncertain"
            status = "uncertain"
            message = "Liveness check uncertain - please try again"
        else:
            label = "not_live"
            status = "failed"
            message = "Liveness check failed - possible spoofing attempt"

        return {
            "status": status,
            "liveness_score": round(liveness_score, 1),
            "label": label,
            "message": message,
            "components": {
                "mini_fasnet": mini_fasnet_result,
            },
        }

    async def check_liveness(self, image_bytes: bytes) -> dict:
        return await asyncio.to_thread(self.check_liveness_sync, image_bytes)
