"""Liveness (presentation attack detection).

Two mechanisms, mirroring how Rekognition offers liveness:

1. Passive, single image: an ensemble of MiniFASNetV2 + MiniFASNetV1SE
   (Silent-Face-Anti-Spoofing, Apache-2.0). Runs on every
   SearchFacesByImage call in ~10 ms, so it can gate attendance without any
   change to the client.

2. Session based (CreateFaceLivenessSession / GetFaceLivenessSessionResults):
   the device captures a short burst of frames while the screen flashes a
   random colour sequence. We combine
     * passive score on every frame,
     * whether the face reflects the random colour sequence (defeats replayed
       videos and injected streams that cannot know the sequence in advance),
     * temporal checks: natural micro-motion (defeats a static photo injected
       as frames), one consistent identity, exactly one face.

Preprocessing follows the original Silent-Face-Anti-Spoofing code: BGR, crop
around the face box at a model specific scale, resize to 80x80, raw 0-255
values, class index 1 = real face.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

LIVE_CLASS = 1


def _scaled_box(src_w: int, src_h: int, box: np.ndarray, scale: float) -> tuple[int, int, int, int]:
    x, y, bw, bh = (float(v) for v in box)
    scale = min((src_h - 1) / bh, min((src_w - 1) / bw, scale))
    nw, nh = bw * scale, bh * scale
    cx, cy = x + bw / 2, y + bh / 2
    x1, y1, x2, y2 = cx - nw / 2, cy - nh / 2, cx + nw / 2, cy + nh / 2
    if x1 < 0:
        x2 -= x1
        x1 = 0
    if y1 < 0:
        y2 -= y1
        y1 = 0
    if x2 > src_w - 1:
        x1 -= x2 - src_w + 1
        x2 = src_w - 1
    if y2 > src_h - 1:
        y1 -= y2 - src_h + 1
        y2 = src_h - 1
    return int(x1), int(y1), int(x2), int(y2)


class _FASModel:
    def __init__(self, path: Path, scale: float, threads: int):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.scale = scale

    def probs(self, image: np.ndarray, box: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        x1, y1, x2, y2 = _scaled_box(w, h, box, self.scale)
        crop = image[y1 : y2 + 1, x1 : x2 + 1]
        crop = cv2.resize(crop, (80, 80))
        blob = crop.astype(np.float32).transpose(2, 0, 1)[None]
        logits = self.session.run(None, {self.input_name: blob})[0][0].astype(np.float64)
        e = np.exp(logits - logits.max())
        return e / e.sum()


class PassiveLiveness:
    def __init__(self, models_dir: Path, threads: int = 1):
        specs = [("MiniFASNetV2.onnx", 2.7), ("MiniFASNetV1SE.onnx", 4.0)]
        self.models = [
            _FASModel(models_dir / name, scale, threads)
            for name, scale in specs
            if (models_dir / name).exists()
        ]

    @property
    def available(self) -> bool:
        return bool(self.models)

    def score(self, image: np.ndarray, box: np.ndarray) -> float:
        """Probability (0-1) that the face is a live person, not a spoof."""
        if not self.models:
            return 1.0
        p = np.mean([m.probs(image, box) for m in self.models], axis=0)
        return float(p[LIVE_CLASS])


# --------------------------------------------------------------------------
# Session (multi-frame) analysis
# --------------------------------------------------------------------------

# Colours the client flashes full-screen, as linear RGB 0-1.
CHALLENGE_COLOURS: dict[str, tuple[float, float, float]] = {
    "white": (1.0, 1.0, 1.0),
    "red": (1.0, 0.0, 0.0),
    "green": (0.0, 1.0, 0.0),
    "blue": (0.0, 0.0, 1.0),
    "yellow": (1.0, 1.0, 0.0),
    "cyan": (0.0, 1.0, 1.0),
    "magenta": (1.0, 0.0, 1.0),
}


@dataclass
class FrameObservation:
    colour: str
    face_count: int
    passive: float | None = None
    # Mean BGR of the central face region.
    face_bgr: np.ndarray | None = None
    embedding: np.ndarray | None = None
    landmarks: np.ndarray | None = None
    box: np.ndarray | None = None
    gray_small: np.ndarray | None = None
    # Mean luminance (0-255) of the face and of everything around it.
    face_luma: float | None = None
    background_luma: float | None = None
    # Face box width as a fraction of the frame width (distance from camera).
    face_fraction: float | None = None


@dataclass
class SessionVerdict:
    confidence: float  # 0-100, Rekognition semantics
    components: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    # User-facing retry guidance, using Rekognition's Face Liveness feedback
    # codes where one exists (plus SCREEN_TOO_DIM and MULTIPLE_FACES).
    feedback: list[str] = field(default_factory=list)


# Lighting limits, tuned on the October 2026 device tests. The kiosk's
# on-device pre-check, if any, should use gentler versions of the same rules.
DARK_FACE_LUMA = 60.0
# A dark room where only the screen lights the face: the face can look bright
# enough while everything around it is near black.
DARK_ROOM_BACKGROUND_LUMA = 55.0
BACKLIGHT_DELTA = 60.0
BACKLIGHT_MIN_BACKGROUND = 120.0
# Below this mean chroma shift the screen flash barely reaches the face.
WEAK_FLASH_MAGNITUDE = 0.0025
# A face narrower than this share of the frame is too far from the screen to
# catch its flashes (measured: genuine checks at ~0.17 failed, at ~0.25 passed).
FACE_TOO_FAR_FRACTION = 0.20


def lighting_feedback(face_luma: float, background_luma: float) -> list[str]:
    # Backlight first: a face in shadow against a bright window is "dark", but
    # the useful advice is to turn away from the light, not to find more light.
    if background_luma - face_luma > BACKLIGHT_DELTA and background_luma > BACKLIGHT_MIN_BACKGROUND:
        return ["HIGH_LIGHTING_DETECTED"]
    if face_luma < DARK_FACE_LUMA or background_luma < DARK_ROOM_BACKGROUND_LUMA:
        return ["LOW_LIGHTING_DETECTED"]
    return []


def _chroma(bgr: np.ndarray) -> np.ndarray:
    """Chromaticity (r, g, b) / sum - removes overall brightness changes."""
    rgb = bgr[::-1].astype(np.float64) + 1.0
    return rgb / rgb.sum()


def flash_response_score(obs: list[FrameObservation]) -> tuple[float, dict]:
    """How well the face colour follows the random flash sequence.

    For every pair of frames lit by different colours we compare the observed
    change in face chromaticity with the change expected from the screen
    colours. Live skin, a few dozen centimetres from a bright screen, shifts
    towards the displayed colour. A pre-recorded or injected video cannot
    follow a random sequence it has not seen.
    """
    pts = [o for o in obs if o.face_bgr is not None and o.colour in CHALLENGE_COLOURS]
    expected, observed = [], []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            a, b = pts[i], pts[j]
            if a.colour == b.colour:
                continue
            ea = np.array(CHALLENGE_COLOURS[a.colour]) + 0.15
            eb = np.array(CHALLENGE_COLOURS[b.colour]) + 0.15
            expected.append((eb / eb.sum()) - (ea / ea.sum()))
            observed.append(_chroma(b.face_bgr) - _chroma(a.face_bgr))
    if len(expected) < 3:
        return 0.0, {"pairs": len(expected), "correlation": None}
    e = np.concatenate(expected)
    o = np.concatenate(observed)
    if np.std(o) < 1e-6:
        return 0.0, {"pairs": len(expected), "correlation": 0.0, "magnitude": 0.0}
    corr = float(np.corrcoef(e, o)[0, 1])
    magnitude = float(np.mean(np.abs(o)))
    # Correlation carries the signal; very small magnitudes are noise.
    score = max(0.0, corr) * min(1.0, magnitude / 0.004)
    return float(score), {"pairs": len(expected), "correlation": round(corr, 4), "magnitude": round(magnitude, 5)}


def motion_score(obs: list[FrameObservation]) -> tuple[float, dict]:
    """Natural micro-motion between frames.

    Identical frames (a still photo injected into the stream) score 0. Wild
    jumps (frames stitched from different sources) score low too.
    """
    lms = [o.landmarks for o in obs if o.landmarks is not None and o.box is not None]
    boxes = [o.box for o in obs if o.landmarks is not None and o.box is not None]
    if len(lms) < 3:
        return 0.0, {"frames": len(lms)}
    shifts = []
    for k in range(1, len(lms)):
        size = max(float(boxes[k][2]), 1.0)
        shifts.append(float(np.mean(np.linalg.norm(lms[k] - lms[k - 1], axis=1))) / size)
    mean_shift = float(np.mean(shifts))
    # 0.2% .. 8% of face width per frame is what a hand-held / kiosk capture shows.
    if mean_shift < 0.0015:
        score = mean_shift / 0.0015 * 0.3
    elif mean_shift > 0.12:
        score = 0.2
    else:
        score = 1.0
    grays = [o.gray_small for o in obs if o.gray_small is not None]
    pixel_delta = (
        float(np.mean([np.mean(np.abs(grays[k].astype(np.int16) - grays[k - 1])) for k in range(1, len(grays))]))
        if len(grays) > 1
        else 0.0
    )
    if pixel_delta < 0.5:
        score = min(score, 0.1)
    return score, {"mean_landmark_shift": round(mean_shift, 5), "pixel_delta": round(pixel_delta, 3)}


def identity_consistency(obs: list[FrameObservation]) -> tuple[float, dict]:
    embs = [o.embedding for o in obs if o.embedding is not None]
    if len(embs) < 2:
        return 0.0, {"frames": len(embs)}
    ref = embs[0]
    sims = [float(np.dot(ref, e)) for e in embs[1:]]
    worst = min(sims)
    return (1.0 if worst >= 0.45 else 0.0), {"min_similarity_to_first": round(worst, 4)}


def judge_session(obs: list[FrameObservation], frames_required: int, mode: str = "flash") -> SessionVerdict:
    """mode="flash": colour-flash challenge (passive PAD + flash response +
    motion). mode="passive": plain frames without a challenge (passive PAD +
    motion + identity). Passive mode cannot detect frames injected straight
    into the API, because no unpredictable challenge links the frames to this
    session; it still stops photos, screens and prints held to a camera."""
    reasons: list[str] = []
    with_face = [o for o in obs if o.face_count == 1]
    if len(obs) < frames_required:
        reasons.append("TOO_FEW_FRAMES")
    if any(o.face_count > 1 for o in obs):
        reasons.append("MULTIPLE_FACES")
    if len(with_face) < max(3, int(0.8 * len(obs))):
        reasons.append("FACE_NOT_VISIBLE")

    # Passive PAD is judged on the neutral (white) frames only: the model was
    # trained on normally lit faces, and strong coloured light makes a real
    # face look unfamiliar to it (measured: genuine scores drop from ~0.99 to
    # ~0.6 under a bright flash). Coloured frames feed the flash, motion and
    # identity checks instead.
    neutral = with_face if mode == "passive" else ([o for o in with_face if o.colour == "white"] or with_face)
    passive_vals = [o.passive for o in neutral if o.passive is not None]
    passive = float(np.mean(passive_vals)) if passive_vals else 0.0
    passive_min = float(np.min(passive_vals)) if passive_vals else 0.0
    flash, flash_info = flash_response_score(with_face) if mode != "passive" else (0.0, {})
    motion, motion_info = motion_score(with_face)
    ident, ident_info = identity_consistency(with_face)
    if ident == 0.0:
        reasons.append("IDENTITY_CHANGED")
    if motion <= 0.1:
        reasons.append("NO_NATURAL_MOTION")

    # Passive PAD is the strongest single signal and scales everything; the
    # flash response and natural motion are the evidence that this is a live
    # capture of a 3D face in front of *this* screen, not a replay/injection.
    if mode == "passive":
        combined = passive * (0.80 + 0.20 * motion)
    else:
        combined = passive * (0.45 + 0.35 * flash + 0.20 * motion)
    # A single clearly-spoof frame should be able to sink the session.
    if passive_min < 0.15:
        combined = min(combined, passive_min * 2)
        reasons.append("SPOOF_FRAME_DETECTED")
    hard_fail = ("TOO_FEW_FRAMES", "MULTIPLE_FACES", "FACE_NOT_VISIBLE", "IDENTITY_CHANGED", "NO_NATURAL_MOTION")
    if any(r in reasons for r in hard_fail):
        combined = min(combined, 0.2)
    confidence = round(float(np.clip(combined, 0, 1)) * 100.0, 3)

    feedback: list[str] = []
    if "FACE_NOT_VISIBLE" in reasons:
        feedback.append("FACE_NOT_VISIBLE")
    if "MULTIPLE_FACES" in reasons or "IDENTITY_CHANGED" in reasons:
        feedback.append("MULTIPLE_FACES")
    lit = [o for o in neutral if o.face_luma is not None and o.background_luma is not None]
    face_luma = float(np.median([o.face_luma for o in lit])) if lit else None
    background_luma = float(np.median([o.background_luma for o in lit])) if lit else None
    if lit:
        feedback += lighting_feedback(face_luma, background_luma)
    fractions = [o.face_fraction for o in with_face if o.face_fraction is not None]
    face_fraction = float(np.median(fractions)) if fractions else None
    if face_fraction is not None and face_fraction < FACE_TOO_FAR_FRACTION:
        feedback.append("FACE_TOO_FAR")
    magnitude = flash_info.get("magnitude")
    if magnitude is not None and magnitude < WEAK_FLASH_MAGNITUDE and "LOW_LIGHTING_DETECTED" not in feedback:
        feedback.append("SCREEN_TOO_DIM")
    if "SPOOF_FRAME_DETECTED" in reasons:
        # A clear presentation attack: no coaching on how to do better.
        feedback = []

    return SessionVerdict(
        confidence=confidence,
        feedback=feedback,
        reasons=reasons,
        components={
            "mode": mode,
            "passive_mean": round(passive, 4),
            "passive_min": round(passive_min, 4),
            "flash": round(flash, 4),
            "flash_detail": flash_info,
            "motion": round(motion, 4),
            "motion_detail": motion_info,
            "identity": ident_info,
            "frames": len(obs),
            "frames_with_one_face": len(with_face),
            "face_luma": None if face_luma is None else round(face_luma, 1),
            "background_luma": None if background_luma is None else round(background_luma, 1),
            "face_fraction": None if face_fraction is None else round(face_fraction, 3),
        },
    )
