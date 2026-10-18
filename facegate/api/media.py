"""Turn uploaded liveness media into a short burst of frames.

Liveness vendors such as Oz take a short selfie video (~0.7 s) or a "shot
set" (a ZIP of frames) instead of individual photos. Both are reduced here to
the same input /v1/liveness/check analyses: a handful of evenly spaced frames.
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile

import cv2
import numpy as np

from facegate.engine.pipeline import ImageDecodeError, decode_image

# Frames analysed per clip: matches the 7-frame burst of the capture page.
FRAMES_PER_CLIP = 7
MAX_VIDEO_FRAMES = 900  # 30 s at 30 fps: anything longer is not a selfie clip
MAX_ARCHIVE_ENTRIES = 300
MAX_ARCHIVE_UNCOMPRESSED = 60 * 1024 * 1024
FRAME_MAX_SIDE = 640  # the size the capture page sends


class MediaError(ValueError):
    pass


def _shrink(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    s = FRAME_MAX_SIDE / max(h, w)
    if s >= 1:
        return img
    return cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


def _evenly(items: list, n: int) -> list:
    if len(items) <= n:
        return items
    idx = np.linspace(0, len(items) - 1, n).round().astype(int)
    return [items[i] for i in idx]


def frames_from_video(data: bytes) -> list[np.ndarray]:
    """Decode an MP4/MOV/WebM clip and return evenly spaced frames.

    OpenCV's FFmpeg backend needs a file, so the clip is written to a
    temporary file (tmpfs in the container) and removed straight away.
    Rotation metadata from phones is applied by OpenCV."""
    fd, path = tempfile.mkstemp(suffix=".video")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise MediaError("The video could not be read (use MP4, MOV or WebM).")
        frames = []
        while len(frames) < MAX_VIDEO_FRAMES:
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(_shrink(frame))
        cap.release()
    finally:
        os.remove(path)
    if len(frames) < 3:
        raise MediaError("The video has fewer than 3 frames.")
    # Evenly spaced raw frames (no de-duplication: dropping near-identical
    # frames would hide a still image that was encoded as a video). The
    # spacing (~100 ms in a 0.7 s clip) steps past the duplicate frames some
    # phones insert in low light.
    return _evenly(frames, FRAMES_PER_CLIP)


def frames_from_archive(data: bytes) -> list[np.ndarray]:
    """Read a ZIP of JPEG/PNG frames ("shot set"), in file-name order."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise MediaError("The archive is not a valid ZIP file.") from exc
    entries = [i for i in zf.infolist() if not i.is_dir() and i.filename.lower().endswith((".jpg", ".jpeg", ".png"))]
    if len(entries) > MAX_ARCHIVE_ENTRIES or sum(i.file_size for i in entries) > MAX_ARCHIVE_UNCOMPRESSED:
        raise MediaError("The archive is too large.")
    entries.sort(key=lambda i: i.filename)
    frames = []
    for info in _evenly(entries, FRAMES_PER_CLIP):
        try:
            frames.append(_shrink(decode_image(zf.read(info))))
        except ImageDecodeError as exc:
            raise MediaError(f"{info.filename} is not a readable image.") from exc
    if len(frames) < 3:
        raise MediaError("The archive must contain at least 3 JPEG or PNG frames.")
    return frames
