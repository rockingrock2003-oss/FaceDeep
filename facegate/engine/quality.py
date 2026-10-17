"""Face quality and head pose, reported in Rekognition's FaceDetail format.

Rekognition reports Quality.Brightness / Quality.Sharpness (0-100) and
Pose.Roll / Yaw / Pitch (degrees). Its QualityFilter (LOW/MEDIUM/HIGH/AUTO)
uses these to refuse poor faces. We reproduce the same fields and filter
levels; the numeric scales are our own but follow the same direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class FaceQuality:
    brightness: float  # 0-100
    sharpness: float  # 0-100
    roll: float
    yaw: float
    pitch: float


def estimate_pose(landmarks: np.ndarray) -> tuple[float, float, float]:
    """Approximate roll / yaw / pitch from the five landmarks.

    Good to roughly +-10 degrees for |yaw| < 60, which is all a quality gate
    needs. Positive yaw = face turned towards the image's left.
    """
    eye_r, eye_l, nose, mouth_r, mouth_l = (landmarks[i].astype(np.float64) for i in range(5))
    dx, dy = eye_l - eye_r
    roll = math.degrees(math.atan2(dy, dx))

    # Undo roll so the remaining geometry is axis aligned.
    c, s = math.cos(-math.radians(roll)), math.sin(-math.radians(roll))
    rot = np.array([[c, -s], [s, c]])
    centre = (eye_r + eye_l) / 2
    pts = [(rot @ (p - centre)) for p in (eye_r, eye_l, nose, mouth_r, mouth_l)]
    eye_r, eye_l, nose, mouth_r, mouth_l = pts

    ipd = max(np.linalg.norm(eye_l - eye_r), 1e-6)
    eye_mid = (eye_r + eye_l) / 2
    mouth_mid = (mouth_r + mouth_l) / 2

    # Yaw: horizontal offset of the nose tip from the eye-mouth midline. The
    # nose protrudes roughly 0.6 * IPD in front of the eye plane.
    mid_x = (eye_mid[0] + mouth_mid[0]) / 2
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, (nose[0] - mid_x) / (0.6 * ipd)))))

    # Pitch: where the nose tip sits between the eye line and the mouth line.
    # About 0.48 for a frontal face in the aligned template.
    span = max(mouth_mid[1] - eye_mid[1], 1e-6)
    ratio = (nose[1] - eye_mid[1]) / span
    pitch = (0.48 - ratio) * 120.0
    return roll, -yaw, max(-90.0, min(90.0, pitch))


def measure_quality(image: np.ndarray, box: np.ndarray, aligned: np.ndarray, landmarks: np.ndarray) -> FaceQuality:
    gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
    # Central region of the aligned face avoids background pixels.
    core = gray[24:104, 20:92]
    brightness = float(np.clip(core.mean() / 255.0 * 100.0, 0, 100))
    lap_var = float(cv2.Laplacian(core, cv2.CV_64F).var())
    # log mapping: var 10 -> ~25, 100 -> ~58, 1000 -> ~92
    sharpness = float(np.clip((math.log10(lap_var + 1.0)) * 33.0, 0, 100))
    roll, yaw, pitch = estimate_pose(landmarks)
    return FaceQuality(brightness, sharpness, roll, yaw, pitch)


# Quality filter levels, used by IndexFaces / SearchFacesByImage / CompareFaces.
# AUTO behaves like MEDIUM, as in Rekognition.
FILTER_LEVELS = {
    "LOW": dict(min_conf=0.60, min_px=40, min_sharp=15, bright=(8, 97), max_yaw=60, max_pitch=50),
    "MEDIUM": dict(min_conf=0.70, min_px=60, min_sharp=25, bright=(15, 95), max_yaw=45, max_pitch=35),
    "HIGH": dict(min_conf=0.80, min_px=80, min_sharp=35, bright=(20, 92), max_yaw=30, max_pitch=25),
}
FILTER_LEVELS["AUTO"] = FILTER_LEVELS["MEDIUM"]


def quality_reasons(level: str, q: FaceQuality, score: float, box: np.ndarray) -> list[str]:
    """Return Rekognition UnindexedFaces reasons, empty list if the face passes."""
    if level == "NONE":
        return []
    cfg = FILTER_LEVELS[level]
    reasons: list[str] = []
    if abs(q.yaw) > cfg["max_yaw"] or abs(q.pitch) > cfg["max_pitch"]:
        reasons.append("EXTREME_POSE")
    if q.brightness < cfg["bright"][0]:
        reasons.append("LOW_BRIGHTNESS")
    if q.sharpness < cfg["min_sharp"]:
        reasons.append("LOW_SHARPNESS")
    if score < cfg["min_conf"]:
        reasons.append("LOW_CONFIDENCE")
    if min(box[2], box[3]) < cfg["min_px"]:
        reasons.append("SMALL_BOUNDING_BOX")
    if q.brightness > cfg["bright"][1]:
        reasons.append("LOW_FACE_QUALITY")
    return reasons
