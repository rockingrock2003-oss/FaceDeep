"""The face engine: decode -> detect -> align -> quality -> embed -> liveness."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from facegate.config import Settings
from facegate.engine.calibration import SimilarityCalibration
from facegate.engine.detector import DetectedFace, YuNetDetector
from facegate.engine.embedder import Embedder, align_face
from facegate.engine.liveness import PassiveLiveness
from facegate.engine.quality import FaceQuality, measure_quality, quality_reasons


class ImageDecodeError(ValueError):
    pass


@dataclass
class AnalyzedFace:
    det: DetectedFace
    quality: FaceQuality
    aligned: np.ndarray
    embedding: np.ndarray | None = None
    liveness: float | None = None

    @property
    def box(self) -> np.ndarray:
        return self.det.box

    @property
    def confidence(self) -> float:
        return self.det.score

    def reasons(self, level: str) -> list[str]:
        return quality_reasons(level, self.quality, self.det.score, self.det.box)


@dataclass
class Analysis:
    width: int
    height: int
    image: np.ndarray
    faces: list[AnalyzedFace]
    timings_ms: dict = field(default_factory=dict)


def decode_image(data: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes. IMREAD_COLOR applies the EXIF orientation, so
    iPhone/iPad photos taken in portrait come out upright - the same thing
    Rekognition does."""
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ImageDecodeError("Request has invalid image format")
    return img


class FaceEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.detector = YuNetDetector(
            settings.model_path(settings.detector_model),
            score_threshold=settings.detect_score_threshold,
            max_side=settings.detect_max_side,
        )
        self.embedder = Embedder(
            settings.model_path(settings.recognizer_model),
            kind=settings.recognizer_kind,
            threads=settings.onnx_threads,
            flip_augment=settings.flip_augment,
        )
        self.liveness = PassiveLiveness(settings.models_dir, threads=1)
        self.calibration = SimilarityCalibration.load(settings.model_path(settings.calibration_file))

    @property
    def model_id(self) -> str:
        return self.embedder.name

    def analyze(
        self,
        image: np.ndarray,
        *,
        embed: str = "none",  # "none" | "largest" | "all"
        liveness: str = "none",  # "none" | "largest"
        max_faces: int | None = None,
        purpose: str = "probe",  # "enrol" templates get flip augmentation
    ) -> Analysis:
        t0 = time.perf_counter()
        h, w = image.shape[:2]
        dets: list[DetectedFace] = []
        fast = self.settings.fast_detect_side
        if max_faces == 1 and fast and max(h, w) > fast:
            # Check-in selfies: the face fills much of the frame, so a coarse
            # pass is enough to find it (~4x cheaper). Landmarks are mapped
            # back and alignment still uses the full-resolution image.
            coarse = self.detector.detect(image, max_side=fast)
            if coarse and min(coarse[0].box[2], coarse[0].box[3]) * fast / max(h, w) >= 40:
                dets = coarse
        if not dets:
            dets = self.detector.detect(image)
        dets = [d for d in dets if min(d.box[2], d.box[3]) >= self.settings.min_face_px]
        t1 = time.perf_counter()
        if max_faces is not None:
            dets = dets[:max_faces]
        faces: list[AnalyzedFace] = []
        for d in dets:
            aligned = align_face(image, d.landmarks)
            faces.append(AnalyzedFace(det=d, quality=measure_quality(image, d.box, aligned, d.landmarks), aligned=aligned))
        t2 = time.perf_counter()
        targets = faces if embed == "all" else faces[:1] if embed == "largest" else []
        flip = self.settings.flip_augment if purpose == "enrol" else self.settings.flip_augment_probe
        for f in targets:
            f.embedding = self.embedder.embed(f.aligned, flip=flip)
        t3 = time.perf_counter()
        if liveness == "largest" and faces:
            faces[0].liveness = self.liveness.score(image, faces[0].box)
        t4 = time.perf_counter()
        return Analysis(
            width=w,
            height=h,
            image=image,
            faces=faces,
            timings_ms={
                "detect": round((t1 - t0) * 1000, 2),
                "align_quality": round((t2 - t1) * 1000, 2),
                "embed": round((t3 - t2) * 1000, 2),
                "liveness": round((t4 - t3) * 1000, 2),
            },
        )

    def similarity(self, cosine: float) -> float:
        return float(self.calibration.to_similarity(cosine))

    def cosine_for(self, similarity_threshold: float) -> float:
        return self.calibration.to_cosine(similarity_threshold)
