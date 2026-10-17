"""Unit tests for the session liveness judgement using synthetic captures.

A "live" capture is simulated from a real photo by adding what a camera sees
when a real face sits in front of a flashing screen: small head movement and a
colour cast that follows the displayed colour. Attacks are simulated by
breaking one of those properties.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from facegate.config import Settings
from facegate.engine.liveness import CHALLENGE_COLOURS, judge_session
from facegate.engine.pipeline import FaceEngine, decode_image
from facegate.api.liveness_sessions import _observe
from tests.conftest import image

SEQ = ["white", "red", "blue", "green", "magenta", "yellow"]


@pytest.fixture(scope="module")
def engine():
    return FaceEngine(Settings(environment="test"))


def _frame(base: np.ndarray, colour: str, k: int, rng: np.random.Generator, tint: float = 0.10, move: bool = True) -> np.ndarray:
    h, w = base.shape[:2]
    img = base.astype(np.float32)
    if move:
        dx, dy = rng.normal(0, 1.5, 2)
        ang = rng.normal(0, 0.8)
        m = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0 + 0.004 * k)
        m[:, 2] += (dx, dy)
        img = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)
    r, g, b = CHALLENGE_COLOURS[colour]
    cast = np.array([b, g, r], dtype=np.float32)  # BGR
    img = img * (1 - tint) + img * cast * tint * 1.6
    img += rng.normal(0, 1.2, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _observations(engine, frames, colours):
    return [_observe(engine, f, c) for f, c in zip(frames, colours)]


def test_simulated_live_capture_passes(engine):
    base = decode_image(image("George_W_Bush_0001.jpg"))
    rng = np.random.default_rng(1)
    frames = [_frame(base, c, k, rng) for k, c in enumerate(SEQ)]
    v = judge_session(_observations(engine, frames, SEQ), frames_required=6)
    assert v.components["flash"] > 0.5, v.components
    assert v.confidence >= 70, v


def test_static_photo_injection_fails(engine):
    base = decode_image(image("George_W_Bush_0001.jpg"))
    v = judge_session(_observations(engine, [base] * 6, SEQ), frames_required=6)
    assert "NO_NATURAL_MOTION" in v.reasons
    assert v.confidence < 30


def test_replayed_video_ignores_flash_sequence(engine):
    # A pre-recorded video: natural motion, but the colour cast follows some
    # *other* sequence than the one the server asked for.
    base = decode_image(image("George_W_Bush_0001.jpg"))
    rng = np.random.default_rng(2)
    recorded = ["white", "green", "yellow", "red", "blue", "cyan"]
    frames = [_frame(base, c, k, rng) for k, c in enumerate(recorded)]
    v = judge_session(_observations(engine, frames, SEQ), frames_required=6)
    assert v.components["flash"] < 0.3, v.components
    assert v.confidence < 70


def test_face_swap_midway_fails(engine):
    a = decode_image(image("George_W_Bush_0001.jpg"))
    b = decode_image(image("Colin_Powell_0001.jpg"))
    rng = np.random.default_rng(3)
    frames = [_frame(a if k < 3 else b, c, k, rng) for k, c in enumerate(SEQ)]
    v = judge_session(_observations(engine, frames, SEQ), frames_required=6)
    assert "IDENTITY_CHANGED" in v.reasons
    assert v.confidence <= 20


def test_too_few_frames_fails(engine):
    base = decode_image(image("George_W_Bush_0001.jpg"))
    rng = np.random.default_rng(4)
    frames = [_frame(base, c, k, rng) for k, c in enumerate(SEQ[:2])]
    v = judge_session(_observations(engine, frames, SEQ[:2]), frames_required=6)
    assert "TOO_FEW_FRAMES" in v.reasons


def test_dark_capture_gets_low_lighting_feedback(engine):
    base = (decode_image(image("George_W_Bush_0001.jpg")).astype(np.float32) * 0.18).astype(np.uint8)
    rng = np.random.default_rng(5)
    seq = ["white", "red", "blue", "white", "green", "magenta", "white"]
    frames = [_frame(base, c, k, rng) for k, c in enumerate(seq)]
    v = judge_session(_observations(engine, frames, seq), frames_required=7)
    assert "LOW_LIGHTING_DETECTED" in v.feedback, (v.feedback, v.components)


def test_clear_spoof_gets_no_coaching(engine):
    from facegate.engine.liveness import FrameObservation

    obs = [FrameObservation(colour=c, face_count=1, passive=0.01) for c in ["white", "red", "blue", "white"]]
    v = judge_session(obs, frames_required=4)
    assert "SPOOF_FRAME_DETECTED" in v.reasons
    assert v.feedback == []
