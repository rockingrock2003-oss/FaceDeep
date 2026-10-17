"""Run the production engine over a face dataset and cache the results.

For every image: detect, pick the face (closest to the image centre, the
standard LFW protocol), align, embed (plain and with flip augmentation) and
score passive liveness. Output: one .npz used by the benchmark scripts.

Usage:
    python -m eval.extract_embeddings --root data/lfw/lfw --out data/eval/lfw_sface.npz
"""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

_engine = None


def _init(threads: int, recognizer_model: str, recognizer_kind: str) -> None:
    global _engine
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    import cv2

    cv2.setNumThreads(1)
    from facegate.config import Settings
    from facegate.engine.pipeline import FaceEngine

    _engine = FaceEngine(
        Settings(onnx_threads=threads, recognizer_model=recognizer_model, recognizer_kind=recognizer_kind)
    )


def _process(path: str):
    from facegate.engine.embedder import align_face
    from facegate.engine.pipeline import decode_image

    e = _engine
    img = decode_image(Path(path).read_bytes())
    h, w = img.shape[:2]
    t0 = time.perf_counter()
    dets = e.detector.detect(img)
    if not dets:
        return path, None, None, None, 0.0, (time.perf_counter() - t0) * 1000
    cx, cy = w / 2, h / 2
    d = min(dets, key=lambda f: (f.box[0] + f.box[2] / 2 - cx) ** 2 + (f.box[1] + f.box[3] / 2 - cy) ** 2)
    aligned = align_face(img, d.landmarks)
    sess, name = e.embedder.session, e.embedder.input_name
    plain = sess.run(None, {name: e.embedder._preprocess(aligned)})[0][0].astype(np.float32)
    import cv2

    flip = sess.run(None, {name: e.embedder._preprocess(cv2.flip(aligned, 1))})[0][0].astype(np.float32)
    live = e.liveness.score(img, d.box)
    ms = (time.perf_counter() - t0) * 1000
    return path, plain, flip, live, float(d.score), ms


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--recognizer-model", default="face_recognition_sface_2021dec.onnx")
    ap.add_argument("--recognizer-kind", default="sface")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    files = sorted(str(p) for p in args.root.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if args.limit:
        files = files[: args.limit]
    print(f"{len(files)} images, {args.workers} workers")
    names, plains, flips, lives, scores, times = [], [], [], [], [], []
    missing = []
    t0 = time.time()
    with ProcessPoolExecutor(
        args.workers, initializer=_init, initargs=(args.threads, args.recognizer_model, args.recognizer_kind)
    ) as pool:
        for i, (path, plain, flip, live, score, ms) in enumerate(pool.map(_process, files, chunksize=16)):
            rel = str(Path(path).relative_to(args.root)).replace("\\", "/")
            if plain is None:
                missing.append(rel)
                continue
            names.append(rel)
            plains.append(plain)
            flips.append(flip)
            lives.append(live)
            scores.append(score)
            times.append(ms)
            if (i + 1) % 1000 == 0:
                print(f"  {i + 1}/{len(files)}  {time.time() - t0:.0f}s", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        names=np.array(names),
        plain=np.stack(plains),
        flip=np.stack(flips),
        liveness=np.array(lives, dtype=np.float32),
        det_score=np.array(scores, dtype=np.float32),
        ms=np.array(times, dtype=np.float32),
        missing=np.array(missing),
    )
    print(f"done: {len(names)} embedded, {len(missing)} without a detected face, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
