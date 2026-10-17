"""Face detection with YuNet (OpenCV Zoo, MIT licence).

YuNet returns a bounding box, five landmarks and a score per face. It runs in
a few milliseconds on a laptop CPU, which is what makes the 200 ms budget easy
to meet without a GPU.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class DetectedFace:
    # Pixel coordinates in the *original* image.
    box: np.ndarray  # [x, y, w, h]
    # 5 x 2 landmarks in image order: right eye (image-left), left eye
    # (image-right), nose tip, right mouth corner, left mouth corner.
    landmarks: np.ndarray
    score: float

    @property
    def area(self) -> float:
        return float(self.box[2] * self.box[3])


class YuNetDetector:
    """Thread-safe wrapper: cv2.FaceDetectorYN keeps per-call state, so each
    worker thread gets its own instance."""

    def __init__(
        self,
        model_path: Path,
        score_threshold: float = 0.6,
        nms_threshold: float = 0.3,
        max_side: int = 640,
    ):
        if not model_path.exists():
            raise FileNotFoundError(f"Detector model not found: {model_path}")
        self.model_path = str(model_path)
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.max_side = max_side
        self._local = threading.local()

    def _instance(self, width: int, height: int) -> cv2.FaceDetectorYN:
        det = getattr(self._local, "det", None)
        if det is None:
            det = cv2.FaceDetectorYN.create(
                self.model_path, "", (width, height), self.score_threshold, self.nms_threshold, 5000
            )
            self._local.det = det
        det.setInputSize((width, height))
        return det

    def detect(self, image: np.ndarray, max_side: int | None = None) -> list[DetectedFace]:
        h, w = image.shape[:2]
        limit = max_side or self.max_side
        scale = 1.0
        work = image
        if max(h, w) > limit:
            scale = limit / max(h, w)
            work = cv2.resize(image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        wh, ww = work.shape[:2]
        _, rows = self._instance(ww, wh).detect(work)
        if rows is None:
            return []
        faces: list[DetectedFace] = []
        inv = 1.0 / scale
        for row in rows:
            box = row[0:4].astype(np.float32) * inv
            lm = row[4:14].reshape(5, 2).astype(np.float32) * inv
            # Clip the box to the image; YuNet can extend slightly outside.
            x1, y1 = max(0.0, box[0]), max(0.0, box[1])
            x2, y2 = min(float(w), box[0] + box[2]), min(float(h), box[1] + box[3])
            if x2 <= x1 or y2 <= y1:
                continue
            faces.append(
                DetectedFace(
                    box=np.array([x1, y1, x2 - x1, y2 - y1], dtype=np.float32),
                    landmarks=lm,
                    score=float(row[14]),
                )
            )
        # Largest face first, the same ordering Rekognition uses for IndexFaces.
        faces.sort(key=lambda f: f.area, reverse=True)
        return faces
