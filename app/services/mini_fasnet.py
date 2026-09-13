from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

MODEL_DIR = Path("models")
MINIFASNET_V1SE_MODEL = MODEL_DIR / "MiniFASNetV1SE.onnx"
MINIFASNET_V2_MODEL = MODEL_DIR / "MiniFASNetV2.onnx"


class MiniFASNetDetector:
    def __init__(self, model_path: Path, crop_scale: float):
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {model_path}. "
                "Download from: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing"
            )
        self.session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape
        self.crop_scale = crop_scale
        self.threshold = 0.5

    def _crop_face(self, frame: np.ndarray, landmarks, w: int, h: int) -> np.ndarray:
        left_cheek = landmarks[234]
        right_cheek = landmarks[454]
        forehead = landmarks[10]
        chin = landmarks[152]

        cx = (left_cheek.x + right_cheek.x) / 2
        cy = (forehead.y + chin.y) / 2

        face_width = abs(right_cheek.x - left_cheek.x) * w
        face_height = abs(chin.y - forehead.y) * h

        crop_size = max(face_width, face_height) * self.crop_scale

        x1 = max(0, int(cx * w - crop_size / 2))
        y1 = max(0, int(cy * h - crop_size / 2))
        x2 = min(w, int(cx * w + crop_size / 2))
        y2 = min(h, int(cy * h + crop_size / 2))

        if x2 <= x1 or y2 <= y1:
            return None

        return frame[y1:y2, x1:x2]

    def _preprocess(self, face_img: np.ndarray) -> np.ndarray:
        h, w = face_img.shape[:2]
        target_size = self.input_shape[2:]

        if h != target_size[0] or w != target_size[1]:
            face_img = cv2.resize(face_img, (target_size[1], target_size[0]))

        face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
        face_img = face_img.astype(np.float32) / 255.0

        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        face_img = (face_img - mean) / std

        face_img = face_img.transpose(2, 0, 1)
        face_img = np.expand_dims(face_img, axis=0)
        return face_img.astype(np.float32)

    def predict(self, frame: np.ndarray, landmarks, w: int, h: int) -> dict:
        face_img = self._crop_face(frame, landmarks, w, h)
        if face_img is None or face_img.size == 0:
            return {
                "is_live": None,
                "live_probability": 0.0,
                "spoof_probability": 0.0,
                "confidence": 0.0,
                "error": "Could not extract face ROI",
            }

        input_data = self._preprocess(face_img)
        outputs = self.session.run(None, {self.input_name: input_data})

        logits = outputs[0][0]
        probs = self._softmax(logits)

        live_prob = float(probs[0])
        spoof_prob = float(probs[1])

        is_live = live_prob > self.threshold

        return {
            "is_live": is_live,
            "live_probability": round(live_prob, 4),
            "spoof_probability": round(spoof_prob, 4),
            "confidence": round(max(live_prob, spoof_prob), 4),
        }

    def _softmax(self, x):
        e_x = np.exp(x - np.max(x))
        return e_x / e_x.sum()


class MiniFASNetEnsemble:
    def __init__(self):
        self.v1se = None
        self.v2 = None

        try:
            self.v1se = MiniFASNetDetector(MINIFASNET_V1SE_MODEL, crop_scale=4.0)
        except FileNotFoundError:
            pass

        try:
            self.v2 = MiniFASNetDetector(MINIFASNET_V2_MODEL, crop_scale=2.7)
        except FileNotFoundError:
            pass

    def predict(self, frame: np.ndarray, landmarks, w: int, h: int) -> dict:
        results = []

        if self.v1se:
            v1se_result = self.v1se.predict(frame, landmarks, w, h)
            if v1se_result["is_live"] is not None:
                results.append(("v1se", v1se_result))

        if self.v2:
            v2_result = self.v2.predict(frame, landmarks, w, h)
            if v2_result["is_live"] is not None:
                results.append(("v2", v2_result))

        if not results:
            return {
                "is_live": None,
                "live_probability": 0.0,
                "spoof_probability": 0.0,
                "confidence": 0.0,
                "models_used": [],
                "error": "No models available",
            }

        avg_live_prob = sum(r["live_probability"] for _, r in results) / len(results)
        avg_spoof_prob = sum(r["spoof_probability"] for _, r in results) / len(results)

        is_live = avg_live_prob > 0.5

        return {
            "is_live": is_live,
            "live_probability": round(avg_live_prob, 4),
            "spoof_probability": round(avg_spoof_prob, 4),
            "confidence": round(max(avg_live_prob, avg_spoof_prob), 4),
            "models_used": [name for name, _ in results],
            "individual_results": {name: r for name, r in results},
        }


@lru_cache
def get_mini_fasnet_ensemble() -> MiniFASNetEnsemble:
    return MiniFASNetEnsemble()

