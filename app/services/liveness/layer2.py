import logging
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from app.core.config import settings

logger = logging.getLogger("facedeep.liveness.layer2")

MODEL_DIR = Path("models")
DEPTH_MODEL_PATH = MODEL_DIR / "dpt_swin2_tiny_256.onnx"


class Layer2DeepContext:
    def __init__(self):
        self._depth_session = None
        self._opencv_cascade = None
        self.threshold = settings.LIVENESS_LAYER2_THRESHOLD
        self._depth_available = False
        self._init_depth_model()

    def _init_depth_model(self):
        if not DEPTH_MODEL_PATH.exists():
            logger.info(f"Depth model not found at {DEPTH_MODEL_PATH}, depth analysis disabled")
            return
        try:
            self._depth_session = ort.InferenceSession(
                str(DEPTH_MODEL_PATH), providers=["CPUExecutionProvider"]
            )
            self._depth_available = True
            logger.info("Depth estimation model loaded")
        except Exception as e:
            logger.warning(f"Failed to load depth model: {e}")

    def _get_cascade(self):
        if self._opencv_cascade is None:
            self._opencv_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
        return self._opencv_cascade

    def _estimate_depth(self, frame: np.ndarray) -> np.ndarray | None:
        if not self._depth_available or self._depth_session is None:
            return None

        try:
            input_meta = self._depth_session.get_inputs()[0]
            _, _, ih, iw = input_meta.shape

            resized = cv2.resize(frame, (iw, ih))
            blob = resized.astype(np.float32).transpose(2, 0, 1) / 255.0
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)
            blob = ((blob - mean) / std).astype(np.float32)
            blob = np.expand_dims(blob, axis=0)

            outputs = self._depth_session.run(None, {input_meta.name: blob})
            depth_map = outputs[0]

            if depth_map.ndim == 4:
                depth_map = depth_map[0, 0]
            elif depth_map.ndim == 3:
                depth_map = depth_map[0]

            depth_map = cv2.resize(depth_map, (frame.shape[1], frame.shape[0]))
            depth_map = (depth_map - depth_map.min()) / (depth_map.max() - depth_map.min() + 1e-8)
            return depth_map

        except Exception as e:
            logger.warning(f"Depth estimation failed: {e}")
            return None

    def _depth_flatness_score(self, depth_map: np.ndarray, face_mask: np.ndarray) -> float:
        face_depth = depth_map[face_mask > 0] if np.any(face_mask > 0) else depth_map.ravel()
        if len(face_depth) == 0:
            return 0.5

        depth_range = float(np.ptp(face_depth))
        depth_std = float(np.std(face_depth))

        flatness = 1.0 - min(depth_range, 1.0)
        variation_score = min(depth_std / 0.15, 1.0)

        return float(flatness * 0.6 + (1.0 - variation_score) * 0.4)

    def _flash_reflection_score(self, frame: np.ndarray, gray: np.ndarray) -> float:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]

        bright_mask = (v_channel > 240).astype(np.float32)
        bright_ratio = np.mean(bright_mask)

        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
        highlights = (l_channel > 220).astype(np.float32)
        highlight_ratio = np.mean(highlights)

        uniformity = 1.0 - min(np.std(v_channel) / 80.0, 1.0)

        if bright_ratio > 0.15 and uniformity > 0.7:
            flash_score = 0.9
        elif highlight_ratio > 0.1:
            flash_score = 0.7
        else:
            flash_score = min((bright_ratio + highlight_ratio) / 0.2, 0.3)

        return float(flash_score)

    def _moire_score(self, gray: np.ndarray) -> float:
        f = np.fft.fft2(gray.astype(np.float64))
        fshift = np.fft.fftshift(f)
        magnitude = np.log(np.abs(fshift) + 1)

        h, w = gray.shape
        cy, cx = h // 2, w // 2

        y, x = np.ogrid[:h, :w]
        dist = np.sqrt((x - cx)**2 + (y - cy)**2)
        max_dist = np.sqrt(cx**2 + cy**2)

        norm_dist = dist / max_dist
        ring_mask1 = ((norm_dist > 0.15) & (norm_dist < 0.30)).astype(np.float32)
        ring_mask2 = (
            (norm_dist > 0.30) & (norm_dist < 0.45)
        ).astype(np.float32)

        ring_energy1 = np.mean(magnitude * ring_mask1) if np.any(ring_mask1) else 0
        ring_energy2 = np.mean(magnitude * ring_mask2) if np.any(ring_mask2) else 0
        total_energy = np.mean(magnitude)

        if total_energy == 0:
            return 0.0

        moire_ratio = (ring_energy1 + ring_energy2) / (2 * total_energy)

        angle_bins = 36
        magnitudes_masked = magnitude * (norm_dist > 0.1).astype(np.float32)
        angles = np.arctan2(y - cy, x - cx)
        angle_hist = np.zeros(angle_bins)
        for b in range(angle_bins):
            lo = -np.pi + (2 * np.pi * b / angle_bins)
            hi = -np.pi + (2 * np.pi * (b + 1) / angle_bins)
            mask = ((angles >= lo) & (angles < hi)).astype(np.float32)
            angle_hist[b] = np.mean(magnitudes_masked * mask)

        angle_std = np.std(angle_hist) / (np.mean(angle_hist) + 1e-8)

        concentric_regularity = 1.0 - min(angle_std / 0.5, 1.0)

        score = min(moire_ratio / 0.3, 1.0) * 0.5 + concentric_regularity * 0.5

        return float(score)

    def _spectral_analysis_score(self, frame: np.ndarray) -> float:
        b, g, r = cv2.split(frame)

        r_mean = np.mean(r.astype(np.float64))
        g_mean = np.mean(g.astype(np.float64))
        b_mean = np.mean(b.astype(np.float64))

        total = r_mean + g_mean + b_mean + 1e-10
        b_ratio = b_mean / total

        blue_shift = max(0, b_ratio - 0.35)

        rg_corr = np.corrcoef(
            r.ravel().astype(np.float64),
            g.ravel().astype(np.float64),
        )[0, 1]

        if blue_shift > 0.02:
            screen_score = min(blue_shift / 0.1, 1.0)
        elif rg_corr < 0.8:
            screen_score = min((1.0 - rg_corr) / 0.3, 1.0)
        else:
            screen_score = 0.1

        return float(screen_score)

    def _face_mask(self, gray: np.ndarray) -> np.ndarray:
        cascade = self._get_cascade()
        faces = cascade.detectMultiScale(gray, 1.1, 4, minSize=(80, 80))
        mask = np.zeros_like(gray)
        if len(faces) > 0:
            x, y, w, h = faces[0]
            mask[y:y + h, x:x + w] = 255
        return mask

    def analyze(self, frame: np.ndarray, gray: np.ndarray) -> dict:
        sub_scores = {}

        face_mask = self._face_mask(gray)

        depth_map = self._estimate_depth(frame)
        if depth_map is not None:
            depth_flat = self._depth_flatness_score(depth_map, face_mask)
            sub_scores["depth_flatness"] = round(depth_flat, 4)
        else:
            depth_flat = 0.3
            sub_scores["depth_flatness"] = round(depth_flat, 4)
            sub_scores["depth_available"] = False

        flash_score = self._flash_reflection_score(frame, gray)
        sub_scores["flash_reflection"] = round(flash_score, 4)

        moire = self._moire_score(gray)
        sub_scores["moire_pattern"] = round(moire, 4)

        spectral = self._spectral_analysis_score(frame)
        sub_scores["spectral_analysis"] = round(spectral, 4)

        spoof_indicators = []
        if depth_flat > 0.7:
            spoof_indicators.append("flat_depth")
        if flash_score > 0.6:
            spoof_indicators.append("screen_flash")
        if moire > 0.7:
            spoof_indicators.append("moire_pattern")
        if spectral > 0.5:
            spoof_indicators.append("blue_shift")

        if len(spoof_indicators) >= 2:
            liveness_score = 20.0
        elif len(spoof_indicators) == 1:
            liveness_score = 45.0
        else:
            liveness_score = 85.0

        sub_scores["spoof_indicators"] = spoof_indicators

        passed = liveness_score >= self.threshold

        return {
            "passed": passed,
            "score": round(liveness_score, 1),
            "detail": "passed" if passed else "deep_context_failed",
            "message": (
                "Layer 2 passed: deep context analysis indicates live face"
                if passed
                else f"Layer 2 failed: detected spoof indicators: {', '.join(spoof_indicators)}"
            ),
            "sub_scores": sub_scores,
        }
