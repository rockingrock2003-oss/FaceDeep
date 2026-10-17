"""Face alignment and embedding.

Two backends:

* ``sface``   - OpenCV Zoo SFace (Apache-2.0), 128-d. The default because its
                licence allows commercial use.
* ``arcface`` - any ArcFace-style ONNX model with a 112x112 input (e.g. a
                commercially licensed InsightFace model). Drop-in upgrade path.

Both use the standard 5-point ArcFace alignment template.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

# Canonical landmark positions for a 112x112 aligned face (ArcFace / SFace).
ARCFACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def align_face(image: np.ndarray, landmarks: np.ndarray, size: int = 112) -> np.ndarray:
    """Similarity-transform the face so its landmarks sit on the template."""
    dst = ARCFACE_TEMPLATE * (size / 112.0)
    matrix, _ = cv2.estimateAffinePartial2D(landmarks.astype(np.float32), dst, method=cv2.LMEDS)
    if matrix is None:
        raise ValueError("Could not align face")
    return cv2.warpAffine(image, matrix, (size, size), borderValue=0.0)


class Embedder:
    def __init__(self, model_path: Path, kind: str = "sface", threads: int = 2, flip_augment: bool = True):
        if not model_path.exists():
            raise FileNotFoundError(f"Recognizer model not found: {model_path}")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(model_path), opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.kind = kind
        self.dim = int(self.session.get_outputs()[0].shape[-1])
        self.flip_augment = flip_augment
        self.name = f"{kind}:{model_path.stem}" + ("+flip" if flip_augment else "")

    def _preprocess(self, aligned_bgr: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
        if self.kind == "arcface":
            rgb = (rgb - 127.5) / 127.5
        # SFace takes raw 0-255 RGB, matching cv2.FaceRecognizerSF.feature().
        return rgb.transpose(2, 0, 1)[None]

    def embed(self, aligned_bgr: np.ndarray, flip: bool | None = None) -> np.ndarray:
        vec = self.session.run(None, {self.input_name: self._preprocess(aligned_bgr)})[0][0].astype(np.float32)
        if flip is None:
            flip = self.flip_augment
        if flip:
            # Flip-averaging ("test-time augmentation") makes the template a
            # little more stable for the price of a second inference.
            vec = vec + self.session.run(
                None, {self.input_name: self._preprocess(cv2.flip(aligned_bgr, 1))}
            )[0][0].astype(np.float32)
        norm = float(np.linalg.norm(vec))
        if norm == 0.0:
            raise ValueError("Zero-norm embedding")
        return vec / norm
