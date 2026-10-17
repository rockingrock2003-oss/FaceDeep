"""Passive-liveness (anti-spoofing) evaluation on your own captures.

Collect images on the real kiosk device:

    data/pad/live/        genuine selfies of colleagues (bona fide)
    data/pad/print/       a printed photo held up to the camera
    data/pad/screen/      a photo / video shown on a phone or laptop screen
    data/pad/<any other attack type>/

Reports the ISO/IEC 30107-3 metrics iBeta uses:
  * APCER - attack presentations wrongly accepted as live (per attack type)
  * BPCER - genuine users wrongly rejected as spoofs
at the configured threshold, plus a threshold sweep.

Usage:
    python -m eval.liveness_eval --root data/pad
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from facegate.config import Settings
from facegate.engine.pipeline import FaceEngine, decode_image


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--live-dir", default="live")
    ap.add_argument("--report", type=Path, default=Path("reports/liveness.json"))
    args = ap.parse_args()

    s = Settings()
    engine = FaceEngine(s)
    scores: dict[str, list[float]] = {}
    no_face: dict[str, int] = {}
    for d in sorted(p for p in args.root.iterdir() if p.is_dir()):
        vals = []
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            a = engine.analyze(decode_image(f.read_bytes()), liveness="largest", max_faces=1)
            if not a.faces:
                no_face[d.name] = no_face.get(d.name, 0) + 1
                continue
            vals.append(a.faces[0].liveness)
        scores[d.name] = vals
    if args.live_dir not in scores:
        raise SystemExit(f"need a '{args.live_dir}' folder with genuine captures")

    th = s.passive_liveness_threshold
    live = np.array(scores[args.live_dir])
    report = {"threshold": th, "counts": {k: len(v) for k, v in scores.items()}, "no_face": no_face}
    report["BPCER"] = float(np.mean(live < th)) if len(live) else None
    report["APCER"] = {k: float(np.mean(np.array(v) >= th)) for k, v in scores.items() if k != args.live_dir and v}
    sweep = []
    attacks = np.concatenate([np.array(v) for k, v in scores.items() if k != args.live_dir and v]) if len(scores) > 1 else np.array([])
    for t in np.arange(0.1, 0.96, 0.05):
        sweep.append(
            {
                "threshold": round(float(t), 2),
                "BPCER": float(np.mean(live < t)) if len(live) else None,
                "APCER_all_attacks": float(np.mean(attacks >= t)) if len(attacks) else None,
            }
        )
    report["sweep"] = sweep
    print(json.dumps({k: report[k] for k in ("threshold", "counts", "BPCER", "APCER")}, indent=2))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
