import logging
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings

logger = logging.getLogger("facedeep.liveness.layer1")

MODEL_DIR = Path("models")
MINIFASNET_V1SE_MODEL = MODEL_DIR / "MiniFASNetV1SE.onnx"
MINIFASNET_V2_MODEL = MODEL_DIR / "MiniFASNetV2.onnx"


class Layer1TextureAnalysis:
    def __init__(self):
        self._mini_fasnet = None
        self._opencv_cascade = None
        self.threshold = settings.LIVENESS_LAYER1_THRESHOLD

    def _get_cascade(self):
        if self._opencv_cascade is None:
            local = Path("models/haarcascade_frontalface_default.xml")
            path = str(local) if local.exists() else (
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            cascade = cv2.CascadeClassifier(path)
            if cascade.empty():
                logger.warning("Haar cascade failed to load from %s", path)
                self._opencv_cascade = False
            else:
                self._opencv_cascade = cascade
        return self._opencv_cascade if self._opencv_cascade is not False else None

    def _get_mini_fasnet(self):
        if self._mini_fasnet is None:
            try:
                from app.services.mini_fasnet import get_mini_fasnet_ensemble
                self._mini_fasnet = get_mini_fasnet_ensemble()
            except Exception:
                pass
        return self._mini_fasnet

    def _get_face_mesh(self):
        try:
            import mediapipe as mp
            if hasattr(mp, "solutions"):
                return mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=True,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                ), False
        except (ImportError, AttributeError):
            pass

        model_path = Path("models/face_landmarker.task")
        if model_path.exists():
            try:
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision
                base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
                options = vision.FaceLandmarkerOptions(
                    base_options=base_options,
                    num_faces=1,
                    min_face_detection_confidence=0.5,
                )
                return vision.FaceLandmarker.create_from_options(options), True
            except Exception as e:
                logger.warning(f"FaceLandmarker init failed: {e}")

        return None, False

    def _optical_flow_score(self, gray: np.ndarray) -> float:
        h, w = gray.shape
        h2, w2 = h // 2, w // 2
        small = cv2.resize(gray, (w2, h2))

        sx = cv2.Sobel(small, cv2.CV_64F, 1, 0, ksize=3)
        sy = cv2.Sobel(small, cv2.CV_64F, 0, 1, ksize=3)
        mag = np.sqrt(sx**2 + sy**2)
        mean_mag = np.mean(mag)
        std_mag = np.std(mag)

        flow_score = min((mean_mag / 30.0) * 0.6 + (std_mag / 20.0) * 0.4, 1.0)
        return float(flow_score)

    def _texture_fft_score(self, gray: np.ndarray) -> float:
        f = np.fft.fft2(gray.astype(np.float64))
        fshift = np.fft.fftshift(f)
        magnitude = np.log(np.abs(fshift) + 1)

        h, w = gray.shape
        cy, cx = h // 2, w // 2
        r = min(h, w) // 4

        y, x = np.ogrid[:h, :w]
        mask = ((x - cx)**2 + (y - cy)**2) <= r**2

        high_freq_energy = np.mean(magnitude[~mask]) if np.any(~mask) else 0
        low_freq_energy = np.mean(magnitude[mask]) if np.any(mask) else 0

        if low_freq_energy == 0:
            return 0.5

        ratio = high_freq_energy / low_freq_energy
        return float(min(max(ratio / 0.6, 0), 1.0))

    def _texture_lbp_score(self, gray: np.ndarray) -> float:
        h, w = gray.shape
        center = gray[1:-1, 1:-1]
        neighbors = [
            gray[0:-2, 0:-2], gray[0:-2, 1:-1], gray[0:-2, 2:],
            gray[1:-1, 2:], gray[2:, 2:], gray[2:, 1:-1],
            gray[2:, 0:-2], gray[1:-1, 0:-2],
        ]

        lbp = np.zeros_like(center, dtype=np.uint8)
        for i, neighbor in enumerate(neighbors):
            lbp |= (neighbor > center).astype(np.uint8) << i

        hist, _ = np.histogram(lbp.ravel(), bins=256, range=(0, 256))
        hist = hist.astype(np.float64) / (hist.sum() + 1e-10)
        entropy = -np.sum(hist[hist > 0] * np.log2(hist[hist > 0]))

        return float(min(entropy / 6.0, 1.0))

    def _detect_skin(self, face_roi: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(face_roi, cv2.COLOR_BGR2HSV)
        lower1 = np.array([0, 20, 70], dtype=np.uint8)
        upper1 = np.array([25, 150, 255], dtype=np.uint8)
        mask1 = cv2.inRange(hsv, lower1, upper1)
        lower2 = np.array([170, 20, 70], dtype=np.uint8)
        upper2 = np.array([180, 150, 255], dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lower2, upper2)
        return mask1 | mask2

    def _minifasnet_score(
        self, frame: np.ndarray, gray: np.ndarray, face_roi: np.ndarray
    ) -> float | None:
        detector = self._get_face_mesh()
        if detector[0] is None:
            return None

        mesh, use_new_api = detector
        h, w = frame.shape[:2]

        if use_new_api:
            import mediapipe as mp
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            results = mesh.detect(mp_image)
            landmarks = results.face_landmarks[0] if results.face_landmarks else None
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = mesh.process(rgb)
            mfl = results.multi_face_landmarks
            landmarks = mfl[0].landmark if mfl else None

        if landmarks is None:
            return None

        mini_fasnet = self._get_mini_fasnet()
        if not mini_fasnet:
            return None

        result = mini_fasnet.predict(frame, landmarks, w, h)
        if result["is_live"] is None:
            return None

        return result["live_probability"]

    def analyze(self, frame: np.ndarray, gray: np.ndarray) -> dict:
        cascade = self._get_cascade()
        if cascade is None:
            return {
                "passed": False,
                "score": 0,
                "detail": "no_cascade",
                "message": "Face detection unavailable (cascade not loaded)",
                "sub_scores": {},
            }
        faces = cascade.detectMultiScale(gray, 1.1, 4, minSize=(80, 80))

        if len(faces) == 0:
            return {
                "passed": False,
                "score": 0,
                "detail": "no_face",
                "message": "No face detected",
                "sub_scores": {},
            }

        x, y, fw, fh = faces[0]
        face_roi = frame[y:y + fh, x:x + fw]
        face_gray = gray[y:y + fh, x:x + fw]

        sub_scores = {}

        minifasnet_score = self._minifasnet_score(frame, gray, face_roi)
        if minifasnet_score is not None:
            sub_scores["minifasnet"] = round(minifasnet_score, 4)

        laplacian_var = cv2.Laplacian(face_gray, cv2.CV_64F).var()
        sub_scores["texture_laplacian"] = round(min(laplacian_var / 150.0, 1.0), 4)

        fft_score = self._texture_fft_score(face_gray)
        sub_scores["texture_fft"] = round(fft_score, 4)

        lbp_score = self._texture_lbp_score(face_gray)
        sub_scores["texture_lbp"] = round(lbp_score, 4)

        flow_score = self._optical_flow_score(gray)
        sub_scores["optical_flow"] = round(flow_score, 4)

        hsv = cv2.cvtColor(face_roi, cv2.COLOR_BGR2HSV)
        v_std = np.std(hsv[:, :, 2])
        brightness_score = min(v_std / 60.0, 1.0)
        sub_scores["brightness"] = round(brightness_score, 4)

        frame_h, frame_w = frame.shape[:2]
        face_ratio = (fw * fh) / (frame_w * frame_h)
        size_score = 1.0 if 0.02 < face_ratio < 0.5 else 0.3
        sub_scores["face_size"] = round(size_score, 4)

        skin_mask = self._detect_skin(face_roi)
        skin_ratio = np.mean(skin_mask) / 255.0 if skin_mask.size > 0 else 0
        skin_score = min(skin_ratio / 0.4, 1.0)
        sub_scores["skin_detection"] = round(skin_score, 4)

        edge_score = min(laplacian_var / 200.0, 1.0)
        sub_scores["edge_sharpness"] = round(edge_score, 4)

        if minifasnet_score is not None:
            liveness_score = minifasnet_score * 100
            sub_scores["method"] = "minifasnet"
        else:
            weights = [0.15, 0.15, 0.10, 0.10, 0.10, 0.15, 0.10, 0.15]
            scores = [
                sub_scores["texture_laplacian"],
                sub_scores["texture_fft"],
                sub_scores["texture_lbp"],
                sub_scores["optical_flow"],
                sub_scores["brightness"],
                sub_scores["face_size"],
                sub_scores["skin_detection"],
                sub_scores["edge_sharpness"],
            ]
            liveness_score = sum(w * s for w, s in zip(weights, scores)) * 100
            sub_scores["method"] = "opencv_heuristic"

        passed = liveness_score >= self.threshold

        return {
            "passed": passed,
            "score": round(liveness_score, 1),
            "detail": "passed" if passed else "texture_analysis_failed",
            "message": (
                "Layer 1 passed: texture analysis indicates live face"
                if passed
                else "Layer 1 failed: possible spoof detected by texture analysis"
            ),
            "sub_scores": sub_scores,
        }
