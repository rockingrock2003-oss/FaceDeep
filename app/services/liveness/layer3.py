import hashlib
import hmac
import logging
import time

import numpy as np

from app.core.config import settings

logger = logging.getLogger("facedeep.liveness.layer3")


class Layer3IntegrityCheck:
    def __init__(self):
        self.max_age_seconds = settings.LIVENESS_MAX_IMAGE_AGE_SECONDS
        secret = settings.LIVENESS_HMAC_SECRET
        self.hmac_secret = secret.encode() if secret else None

    def verify_hmac(
        self,
        image_bytes: bytes,
        signature: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        if signature is None or timestamp is None:
            return {
                "passed": True,
                "score": 100,
                "detail": "no_hmac_configured",
                "message": "HMAC verification skipped (not configured)",
                "sub_scores": {"hmac_valid": True, "skipped": True},
            }

        try:
            ts = int(timestamp)
            age = abs(time.time() - ts)
            if age > self.max_age_seconds:
                return {
                    "passed": False,
                    "score": 0,
                    "detail": "expired",
                    "message": (
                        f"Image timestamp expired "
                        f"({age:.0f}s old, max {self.max_age_seconds}s)"
                    ),
                    "sub_scores": {"hmac_valid": False, "age_seconds": round(age, 1)},
                }
        except (ValueError, TypeError):
            return {
                "passed": False,
                "score": 0,
                "detail": "invalid_timestamp",
                "message": "Invalid timestamp format",
                "sub_scores": {"hmac_valid": False},
            }

        payload = timestamp.encode() + b"." + hashlib.sha256(image_bytes).digest()
        expected = hmac.new(self.hmac_secret, payload, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return {
                "passed": False,
                "score": 0,
                "detail": "invalid_signature",
                "message": "HMAC signature verification failed",
                "sub_scores": {"hmac_valid": False},
            }

        return {
            "passed": True,
            "score": 100,
            "detail": "passed",
            "message": "HMAC signature verified",
            "sub_scores": {"hmac_valid": True, "age_seconds": round(age, 1)},
        }

    def _entropy_score(self, image_bytes: bytes) -> float:
        data = np.frombuffer(image_bytes, dtype=np.uint8)
        hist, _ = np.histogram(data, bins=256, range=(0, 256))
        prob = hist.astype(np.float64) / (data.size + 1e-10)
        prob = prob[prob > 0]
        entropy = -np.sum(prob * np.log2(prob))
        normalized = entropy / 8.0
        return float(min(max(normalized, 0), 1.0))

    def _frequency_entropy_score(self, gray: np.ndarray) -> float:
        f = np.fft.fft2(gray.astype(np.float64))
        magnitude = np.abs(f)
        magnitude = magnitude.ravel()

        hist, _ = np.histogram(magnitude, bins=256)
        prob = hist.astype(np.float64) / (magnitude.size + 1e-10)
        prob = prob[prob > 0]
        entropy = -np.sum(prob * np.log2(prob))
        normalized = entropy / 8.0
        return float(min(max(normalized, 0), 1.0))

    def _compression_artifacts_score(self, gray: np.ndarray) -> float:
        block_size = 8
        h, w = gray.shape
        h = (h // block_size) * block_size
        w = (w // block_size) * block_size
        block_diffs = []

        for i in range(0, h - block_size, block_size):
            for j in range(0, w - block_size, block_size):
                block = gray[i:i + block_size, j:j + block_size].astype(np.float64)
                right_edge = block[:, -1]
                js = j + block_size
                is_ = i + block_size
                next_left = (
                    gray[i:i + block_size, js:js + 1]
                    .ravel().astype(np.float64)
                    if js < w else right_edge
                )
                bottom_edge = block[-1, :]
                next_top = (
                    gray[is_:is_ + 1, j:j + block_size]
                    .ravel().astype(np.float64)
                    if is_ < h else bottom_edge
                )

                diff_h = np.mean(np.abs(right_edge - next_left))
                diff_v = np.mean(np.abs(bottom_edge - next_top))
                block_diffs.append(diff_h + diff_v)

        if not block_diffs:
            return 0.5

        mean_diff = np.mean(block_diffs)
        score = min(mean_diff / 15.0, 1.0)
        return float(score)

    def analyze(
        self,
        frame: np.ndarray,
        gray: np.ndarray,
        image_bytes: bytes,
        signature: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        hmac_result = self.verify_hmac(image_bytes, signature, timestamp)
        sub_scores = dict(hmac_result["sub_scores"])

        if not hmac_result["passed"]:
            return {
                "passed": False,
                "score": 0,
                "detail": hmac_result["detail"],
                "message": hmac_result["message"],
                "sub_scores": sub_scores,
            }

        file_entropy = self._entropy_score(image_bytes)
        sub_scores["file_entropy"] = round(file_entropy, 4)

        freq_entropy = self._frequency_entropy_score(gray)
        sub_scores["frequency_entropy"] = round(freq_entropy, 4)

        compression = self._compression_artifacts_score(gray)
        sub_scores["compression_artifacts"] = round(compression, 4)

        integrity_checks = []

        if file_entropy < 0.3:
            integrity_checks.append("low_file_entropy")
        if freq_entropy < 0.25:
            integrity_checks.append("low_frequency_entropy")
        if compression < 0.15:
            integrity_checks.append("synthetic_compression")

        if len(integrity_checks) >= 2:
            liveness_score = 25.0
        elif len(integrity_checks) == 1:
            liveness_score = 50.0
        else:
            liveness_score = 100.0

        sub_scores["integrity_checks"] = integrity_checks

        passed = liveness_score >= 50.0

        return {
            "passed": passed,
            "score": round(liveness_score, 1),
            "detail": "passed" if passed else "integrity_failed",
            "message": (
                "Layer 3 passed: software integrity check OK"
                if passed
                else f"Layer 3 failed: integrity issues: {', '.join(integrity_checks)}"
            ),
            "sub_scores": sub_scores,
        }
