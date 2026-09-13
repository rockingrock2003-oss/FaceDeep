import asyncio
import logging
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
        self._opencv_face_cascade = None
        self._opencv_available = False

    def _get_opencv_cascade(self):
        if self._opencv_face_cascade is None:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._opencv_face_cascade = cv2.CascadeClassifier(cascade_path)
            self._opencv_available = not self._opencv_face_cascade.empty()
        return self._opencv_face_cascade

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
        return None

    def _init_face_landmarker(self):
        if not LANDMARKER_MODEL_PATH.exists():
            raise FileNotFoundError(f"Face landmarker model not found at {LANDMARKER_MODEL_PATH}")

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

    def _opencv_liveness_check(self, frame: np.ndarray, gray: np.ndarray) -> dict:
        cascade = self._get_opencv_cascade()
        faces = cascade.detectMultiScale(gray, 1.1, 4, minSize=(80, 80))

        if len(faces) == 0:
            return {
                "status": "error",
                "liveness_score": 0,
                "label": "no_face",
                "message": "No face detected in the image",
                "components": {},
            }

        x, y, w, h = faces[0]
        face_roi = frame[y:y + h, x:x + w]

        scores = []

        face_gray = gray[y:y + h, x:x + w]
        laplacian_var = cv2.Laplacian(face_gray, cv2.CV_64F).var()
        texture_score = min(laplacian_var / 150.0, 1.0)
        scores.append(("texture", texture_score))

        hsv = cv2.cvtColor(face_roi, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]
        v_std = np.std(v_channel)
        brightness_variability = min(v_std / 60.0, 1.0)
        scores.append(("brightness", brightness_variability))

        frame_h, frame_w = frame.shape[:2]
        face_ratio = (w * h) / (frame_w * frame_h)
        size_score = 1.0 if 0.02 < face_ratio < 0.5 else 0.3
        scores.append(("size", size_score))

        skin_mask = self._detect_skin(face_roi)
        skin_ratio = np.mean(skin_mask) if skin_mask.size > 0 else 0
        skin_score = min(skin_ratio / 0.4, 1.0)
        scores.append(("skin", skin_score))

        edge_score = min(laplacian_var / 200.0, 1.0)
        scores.append(("edge", edge_score))

        weights = [0.25, 0.15, 0.15, 0.20, 0.25]
        liveness_score = sum(w * s for (_, s), w in zip(scores, weights)) * 100

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
                "method": "opencv_heuristic",
                "scores": {name: round(s, 3) for name, s in scores},
                "laplacian_var": round(laplacian_var, 2),
                "face_detected": True,
            },
        }

    def _detect_skin(self, face_roi: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(face_roi, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 20, 70], dtype=np.uint8)
        upper = np.array([25, 150, 255], dtype=np.uint8)
        mask1 = cv2.inRange(hsv, lower, upper)
        lower2 = np.array([170, 20, 70], dtype=np.uint8)
        upper2 = np.array([180, 150, 255], dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lower2, upper2)
        return mask1 | mask2

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

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        detector = self._get_face_mesh()

        if detector is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if self._use_new_api:
                import mediapipe as mp
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                results = detector.detect(mp_image)
            else:
                results = detector.process(rgb)

            landmarks = self._extract_landmarks(results)

            if landmarks is not None:
                h, w = frame.shape[:2]

                mini_fasnet_detector = self._get_mini_fasnet()
                if mini_fasnet_detector:
                    mini_fasnet_result = mini_fasnet_detector.predict(frame, landmarks, w, h)

                    if mini_fasnet_result["is_live"] is not None:
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
                                "method": "minifasnet",
                                "mini_fasnet": mini_fasnet_result,
                            },
                        }

            return {
                "status": "error",
                "liveness_score": 0,
                "label": "no_face",
                "message": "No face detected in the image",
                "components": {},
            }

        logger.info("MediaPipe unavailable, using OpenCV heuristic liveness")
        return self._opencv_liveness_check(frame, gray)

    async def check_liveness(self, image_bytes: bytes) -> dict:
        return await asyncio.to_thread(self.check_liveness_sync, image_bytes)
