"""Builders for Rekognition response structures (BoundingBox, FaceDetail, ...).

Geometry is expressed as ratios of the image width/height, exactly as
Rekognition does, so client code that draws boxes or crops faces is unchanged.
"""

from __future__ import annotations

import numpy as np

from facegate.engine.pipeline import AnalyzedFace

LANDMARK_TYPES = ["eyeRight", "eyeLeft", "nose", "mouthRight", "mouthLeft"]


def _r(v: float) -> float:
    return float(round(float(v), 8))


def bounding_box(box: np.ndarray, width: int, height: int) -> dict:
    x, y, w, h = (float(v) for v in box)
    return {"Width": _r(w / width), "Height": _r(h / height), "Left": _r(x / width), "Top": _r(y / height)}


def landmarks(face: AnalyzedFace, width: int, height: int) -> list[dict]:
    # YuNet "right eye" is the subject's right eye, which appears on the image
    # left. Rekognition's eyeLeft/eyeRight are also from the subject's view.
    return [
        {"Type": t, "X": _r(p[0] / width), "Y": _r(p[1] / height)}
        for t, p in zip(LANDMARK_TYPES, face.det.landmarks)
    ]


def pose(face: AnalyzedFace) -> dict:
    q = face.quality
    return {"Roll": _r(q.roll), "Yaw": _r(q.yaw), "Pitch": _r(q.pitch)}


def quality(face: AnalyzedFace) -> dict:
    return {"Brightness": _r(face.quality.brightness), "Sharpness": _r(face.quality.sharpness)}


def confidence(face: AnalyzedFace) -> float:
    # Rekognition confidences for real faces are typically 99.9+; YuNet scores
    # for clear faces are 0.85-0.95. A monotone stretch keeps ordering and
    # lets apps that require Confidence > 90/95 behave as before.
    s = float(np.clip(face.confidence, 0.0, 1.0))
    return _r(100.0 * (1.0 - (1.0 - s) ** 3))


def face_detail(face: AnalyzedFace, width: int, height: int) -> dict:
    return {
        "BoundingBox": bounding_box(face.box, width, height),
        "Landmarks": landmarks(face, width, height),
        "Pose": pose(face),
        "Quality": quality(face),
        "Confidence": confidence(face),
    }


def compared_face(face: AnalyzedFace, width: int, height: int) -> dict:
    """ComparedFace shape used by CompareFaces."""
    d = face_detail(face, width, height)
    return {k: d[k] for k in ("BoundingBox", "Confidence", "Landmarks", "Pose", "Quality")}
