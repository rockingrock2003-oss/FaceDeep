"""Map raw cosine similarity onto Rekognition's 0-100 ``Similarity`` scale.

An attendance app was written against Rekognition thresholds, e.g.
``FaceMatchThreshold=90``. For it to keep working unchanged, our Similarity
values must mean roughly the same thing. We anchor the scale on measured
false-accept rates (FAR) from an impostor distribution:

    Similarity  50 -> FAR 1e-1
    Similarity  70 -> FAR 1e-2
    Similarity  80 -> FAR 1e-3   (Rekognition's default threshold)
    Similarity  90 -> FAR 1e-4
    Similarity  95 -> FAR 1e-5
    Similarity  99 -> FAR 1e-6   (AWS's recommendation for high-stakes use)

and map linearly from the 1e-6 point up to cosine 1.0 -> 100. Genuine pairs
of the same person then land at 99+, exactly like Rekognition, so an app using
a 99 threshold still recognises its employees.

The anchors are produced by ``eval/lfw_benchmark.py`` and stored per model in
``models/calibration_<model>.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ANCHOR_SIMILARITIES = [0.0, 50.0, 70.0, 80.0, 90.0, 95.0, 99.0, 100.0]
ANCHOR_FARS = [None, 1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6, None]

# Conservative defaults for SFace, used until a calibration file exists.
# (OpenCV recommends cosine 0.363 as SFace's match threshold.)
DEFAULT_COSINES = [-1.0, 0.20, 0.28, 0.33, 0.38, 0.42, 0.47, 1.0]


class SimilarityCalibration:
    def __init__(self, cosines: list[float], source: str = "default"):
        if len(cosines) != len(ANCHOR_SIMILARITIES):
            raise ValueError("calibration needs one cosine per anchor")
        xs = np.maximum.accumulate(np.array(cosines, dtype=np.float64))
        # Strictly increasing so the mapping is invertible.
        for i in range(1, len(xs)):
            if xs[i] <= xs[i - 1]:
                xs[i] = xs[i - 1] + 1e-6
        self.cosines = xs
        self.sims = np.array(ANCHOR_SIMILARITIES, dtype=np.float64)
        self.source = source

    @classmethod
    def load(cls, path: Path) -> SimilarityCalibration:
        if path.exists():
            data = json.loads(path.read_text())
            return cls(data["cosines"], source=str(path.name))
        return cls(DEFAULT_COSINES)

    def to_similarity(self, cosine: float | np.ndarray) -> float | np.ndarray:
        return np.interp(cosine, self.cosines, self.sims)

    def to_cosine(self, similarity: float) -> float:
        return float(np.interp(similarity, self.sims, self.cosines))

    def describe(self) -> list[dict]:
        return [
            {"similarity": s, "cosine": round(float(c), 4), "far": f}
            for s, c, f in zip(self.sims, self.cosines, ANCHOR_FARS)
        ]


def fit_from_impostors(impostor_scores: np.ndarray) -> list[float]:
    """Compute anchor cosines from a (large) array of impostor cosine scores."""
    scores = np.sort(np.asarray(impostor_scores, dtype=np.float64))
    n = len(scores)
    out = [-1.0]
    for far in ANCHOR_FARS[1:-1]:
        # Score that exactly `far` of impostors exceed.
        k = int(np.ceil((1.0 - far) * n)) - 1
        if far * n < 5:
            # Not enough impostors to observe this FAR directly: extrapolate from
            # a Gaussian tail fitted to the top 1% of impostor scores.
            tail = scores[int(0.99 * n) :]
            mu, sd = float(np.mean(scores)), float(np.std(scores))
            from statistics import NormalDist

            z = NormalDist().inv_cdf(1.0 - far)
            gauss = mu + z * sd
            out.append(max(gauss, float(tail[-1])))
        else:
            out.append(float(scores[min(max(k, 0), n - 1)]))
    out.append(1.0)
    return out
