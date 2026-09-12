import asyncio
from collections import deque

import cv2
import mediapipe as mp
import numpy as np
from scipy.spatial import distance as dist

from app.core.config import settings


class LivenessDetector:
    LEFT_EYE_IDX = [362, 385, 387, 263, 373, 380]
    RIGHT_EYE_IDX = [33, 160, 158, 133, 153, 144]
    MOUTH_IDX = [61, 13, 54, 14, 376, 174, 87, 14, 317, 402, 318, 324, 308, 324, 318, 402, 14, 87, 174, 376]

    def __init__(self):
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        )
        self.ear_threshold = settings.LIVENESS_EAR_THRESHOLD
        self.consec_frames = settings.LIVENESS_CONSEC_FRAMES
        self.min_score = settings.LIVENESS_MIN_SCORE

    def _compute_ear(self, landmarks, eye_indices, w: int, h: int) -> float:
        points = []
        for idx in eye_indices[:6]:
            lm = landmarks[idx]
            points.append((lm.x * w, lm.y * h))

        A = dist.euclidean(points[1], points[5])
        B = dist.euclidean(points[2], points[4])
        C = dist.euclidean(points[0], points[3])

        if C == 0:
            return 0.0
        return (A + B) / (2.0 * C)

    def _compute_mar(self, landmarks, w: int, h: int) -> float:
        mouth_points = []
        indices = [61, 13, 54, 14, 376, 174, 87, 14, 317, 402, 318, 324, 308]
        for idx in indices[:12]:
            lm = landmarks[idx]
            mouth_points.append((lm.x * w, lm.y * h))

        A = dist.euclidean(mouth_points[1], mouth_points[7])
        B = dist.euclidean(mouth_points[2], mouth_points[6])
        C = dist.euclidean(mouth_points[0], mouth_points[4])

        if C == 0:
            return 0.0
        return (A + B) / (2.0 * C)

    def _estimate_head_pose(self, landmarks, w: int, h: int) -> dict:
        model_points = np.array(
            [
                (0.0, 0.0, 0.0),
                (0.0, -330.0, -65.0),
                (-225.0, 170.0, -135.0),
                (225.0, 170.0, -135.0),
                (-150.0, -150.0, -125.0),
                (150.0, -150.0, -125.0),
            ],
            dtype=np.float64,
        )

        key_indices = [1, 152, 33, 263, 61, 291]
        image_points = np.array(
            [(landmarks[i].x * w, landmarks[i].y * h) for i in key_indices],
            dtype=np.float64,
        )

        focal_length = w
        center = (w / 2, h / 2)
        camera_matrix = np.array(
            [
                [focal_length, 0, center[0]],
                [0, focal_length, center[1]],
                [0, 0, 1],
            ],
            dtype=np.float64,
        )

        dist_coeffs = np.zeros((4, 1))

        success, rotation_vec, translation_vec = cv2.solvePnP(
            model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

        rmat, _ = cv2.Rodrigues(rotation_vec)
        angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)

        return {"yaw": float(angles[1]), "pitch": float(angles[0]), "roll": float(angles[2])}

    def _compute_texture_score(self, frame: np.ndarray, landmarks, w: int, h: int) -> float:
        nose_top = landmarks[10]
        chin = landmarks[152]
        left_cheek = landmarks[234]
        right_cheek = landmarks[454]

        x1 = max(0, int(min(left_cheek.x, nose_top.x) * w) - 20)
        y1 = max(0, int(min(nose_top.y, chin.y) * h) - 20)
        x2 = min(w, int(max(right_cheek.x, nose_top.x) * w) + 20)
        y2 = min(h, int(max(nose_top.y, chin.y) * h) + 20)

        if x2 <= x1 or y2 <= y1:
            return 0.0

        face_roi = frame[y1:y2, x1:x2]
        if face_roi.size == 0:
            return 0.0

        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        return float(laplacian_var)

    def _compute_depth_score(self, landmarks) -> dict:
        nose_z = landmarks[1].z
        left_cheek_z = landmarks[234].z
        right_cheek_z = landmarks[454].z

        nose_protrusion = nose_z - (left_cheek_z + right_cheek_z) / 2

        all_z = [landmarks[i].z for i in range(0, 468, 10)]
        depth_spread = max(all_z) - min(all_z)

        return {
            "nose_protrusion": float(nose_protrusion),
            "depth_spread": float(depth_spread),
            "is_3d": depth_spread > 15 and nose_protrusion < -5,
        }

    def _compute_blink_score(self, ear_values: list[float]) -> tuple[int, float]:
        blink_count = 0
        blink_counter = 0

        for ear in ear_values:
            if ear < self.ear_threshold:
                blink_counter += 1
            else:
                if blink_counter >= self.consec_frames:
                    blink_count += 1
                blink_counter = 0

        ear_std = float(np.std(ear_values)) if ear_values else 0.0
        return blink_count, ear_std

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
        results = self.face_mesh.process(rgb)

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

        left_ear = self._compute_ear(landmarks, self.LEFT_EYE_IDX, w, h)
        right_ear = self._compute_ear(landmarks, self.RIGHT_EYE_IDX, w, h)
        avg_ear = (left_ear + right_ear) / 2.0

        blink_count, ear_std = self._compute_blink_score([avg_ear])

        mar = self._compute_mar(landmarks, w, h)

        head_pose = self._estimate_head_pose(landmarks, w, h)

        texture_var = self._compute_texture_score(frame, landmarks, w, h)

        depth_info = self._compute_depth_score(landmarks)

        scores = {}
        scores["blink"] = min(blink_count / 1.0, 1.0) * 100
        scores["ear_movement"] = min(ear_std / 0.05, 1.0) * 100
        pose_movement = abs(head_pose["yaw"]) + abs(head_pose["pitch"])
        scores["pose"] = min(pose_movement / 5.0, 1.0) * 100
        scores["texture"] = min(texture_var / 200.0, 1.0) * 100
        scores["depth"] = 100 if depth_info["is_3d"] else 20

        weights = {
            "blink": 0.25,
            "ear_movement": 0.15,
            "pose": 0.15,
            "texture": 0.25,
            "depth": 0.20,
        }

        total_score = sum(scores[k] * weights[k] for k in weights)

        if total_score >= self.min_score:
            label = "live"
            status = "passed"
            message = "Liveness check passed"
        elif total_score >= self.min_score * 0.5:
            label = "uncertain"
            status = "uncertain"
            message = "Liveness check uncertain - please try again"
        else:
            label = "not_live"
            status = "failed"
            message = "Liveness check failed - possible spoofing attempt"

        return {
            "status": status,
            "liveness_score": round(total_score, 1),
            "label": label,
            "message": message,
            "components": {
                "blink_count": blink_count,
                "ear": round(avg_ear, 4),
                "mar": round(mar, 4),
                "head_pose": {k: round(v, 2) for k, v in head_pose.items()},
                "texture_variance": round(texture_var, 2),
                "depth": depth_info,
                "component_scores": {k: round(v, 1) for k, v in scores.items()},
            },
        }

    async def check_liveness(self, image_bytes: bytes) -> dict:
        return await asyncio.to_thread(self.check_liveness_sync, image_bytes)
