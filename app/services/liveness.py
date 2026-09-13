import asyncio
import logging
import os
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings

logger = logging.getLogger("facedeep.liveness")

LANDMARKER_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "face_landmarker.task"


class LivenessDetector:
    def __init__(self):
        self.face_mesh = None
        self.face_landmarker = None
        self.min_score = settings.LIVENESS_MIN_SCORE
        self._mini_fasnet = None
        self._use_new_api = False

    def _get_face_mesh(self):
        if self.face_mesh is None and self.face_landmarker is None:
            try:
                import mediapipe as mp
                if hasattr(mp, "solutions"):
                    self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                        static_image_mode=True,
                        max_num_faces=1,
                        refine_landmarks=True,
                        min_detection_confidence=0.5,
                    )
                    self._use_new_api = False
                    return self.face_mesh
            except (ImportError, AttributeError):
                pass

            try:
                self._init_face_landmarker()
            except Exception as e:
                logger.warning(f"FaceLandmarker init failed: {e}")

        if self.face_mesh is not None:
            return self.face_mesh
        if self.face_landmarker is not None:
            return self.face_landmarker
        raise ImportError("Neither old nor new mediapipe API available")

    def _init_face_landmarker(self):
        if not LANDMARKER_MODEL_PATH.exists():
            raise FileNotFoundError(f"Face landmarker model not found at {LANDMARKER_MODEL_PATH}")

        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        base_options = mp_python.BaseOptions(model_asset_path=str(LANDMARKER_MODEL_PATH))
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.face_landmarker = vision.FaceLandmarker.create_from_options(options)
        self._use_new_api = True

    def _get_mini_fasnet(self):
        if self._mini_fasnet is None:
            try:
                from app.services.mini_fasnet import get_mini_fasnet_ensemble
                self._mini_fasnet = get_mini_fasnet_ensemble()
            except Exception:
                pass
        return self._mini_fasnet

    def _extract_landmarks(self, results):
        if self._use_new_api:
            if results.face_landmarks:
                return results.face_landmarks[0]
            return None
        else:
            if results.multi_face_landmarks:
                return results.multi_face_landmarks[0].landmark
            return None

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
            detector = self._get_face_mesh()
        except (ImportError, FileNotFoundError) as e:
            return {
                "status": "error",
                "liveness_score": 0,
                "label": "error",
                "message": f"MediaPipe not available: {e}",
                "components": {},
            }

        if self._use_new_api:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            results = detector.detect(mp_image)
        else:
            import mediapipe as mp  # noqa: F811
            results = detector.process(rgb)

        landmarks = self._extract_landmarks(results)
        if landmarks is None:
            return {
                "status": "error",
                "liveness_score": 0,
                "label": "no_face",
                "message": "No face detected in the image",
                "components": {},
            }

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
