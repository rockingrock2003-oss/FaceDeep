"""Accuracy benchmark on LFW, framed the way an attendance system is used.

Produces, from the cached embeddings of ``extract_embeddings.py``:

1. Standard LFW verification accuracy (6,000 pairs, 10-fold) - the number
   face-recognition papers and vendors quote.
2. ROC on *all* genuine and impostor pairs (~240k genuine, ~87M impostor):
   true-accept rate at FAR 1e-3 ... 1e-6.
3. Similarity calibration (cosine -> Rekognition 0-100 scale), written to
   ``models/calibration_<model>.json``.
4. Attendance simulation (open-set 1:N identification):
   - every person with >= 2 photos is an "employee": one photo enrolled,
     every other photo is a check-in attempt;
   - every person with exactly 1 photo is a "stranger" trying to check in;
   - at each Rekognition threshold we count correct check-ins, wrong-person
     check-ins (the dangerous error), false rejections and strangers let in,
   - with and without the twin/look-alike ambiguity guard.

Usage:
    python -m eval.lfw_benchmark --emb data/eval/lfw_sface.npz --pairs data/lfw/pairs.txt
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from facegate.engine.calibration import ANCHOR_FARS, ANCHOR_SIMILARITIES, SimilarityCalibration, fit_from_impostors


def load(path: Path, variant: str):
    d = np.load(path, allow_pickle=False)
    names = [str(n) for n in d["names"]]
    if variant == "flip":
        x = d["plain"] + d["flip"]
    else:
        x = d["plain"].copy()
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    people = [n.split("/")[0] for n in names]
    return names, people, x.astype(np.float32), d


def lfw_pairs(pairs_file: Path, index: dict[str, int]):
    lines = pairs_file.read_text().strip().splitlines()
    out = []
    for ln in lines[1:]:
        p = ln.split("\t")
        if len(p) == 3:
            a = f"{p[0]}/{p[0]}_{int(p[1]):04d}.jpg"
            b = f"{p[0]}/{p[0]}_{int(p[2]):04d}.jpg"
            same = True
        else:
            a = f"{p[0]}/{p[0]}_{int(p[1]):04d}.jpg"
            b = f"{p[2]}/{p[2]}_{int(p[3]):04d}.jpg"
            same = False
        if a in index and b in index:
            out.append((index[a], index[b], same))
    return out


def ten_fold_accuracy(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float, float]:
    folds = np.array_split(np.arange(len(scores)), 10)
    accs, ths = [], []
    cand = np.linspace(-0.2, 1.0, 1201)
    for i, test in enumerate(folds):
        train = np.concatenate([f for j, f in enumerate(folds) if j != i])
        tr_acc = [np.mean((scores[train] >= t) == labels[train]) for t in cand]
        t = cand[int(np.argmax(tr_acc))]
        ths.append(t)
        accs.append(np.mean((scores[test] >= t) == labels[test]))
    return float(np.mean(accs)), float(np.std(accs)), float(np.mean(ths))


def all_pair_scores(x: np.ndarray, people: list[str], chunk: int = 2048):
    labels = np.array(people)
    genuine, impostor_hist = [], np.zeros(4001, dtype=np.int64)  # histogram over [-1, 1] step 0.0005
    impostor_top = []
    n = len(x)
    for s in range(0, n, chunk):
        block = x[s : s + chunk] @ x.T
        for r in range(block.shape[0]):
            i = s + r
            row = block[r, i + 1 :]
            same = labels[i + 1 :] == labels[i]
            genuine.append(row[same])
            imp = row[~same]
            impostor_hist += np.bincount(np.clip(((imp + 1.0) / 0.0005).astype(np.int64), 0, 4000), minlength=4001)
            impostor_top.append(imp[imp > 0.25])
    return np.concatenate(genuine), impostor_hist, np.concatenate(impostor_top)


def tar_at_far(genuine: np.ndarray, impostor_hist: np.ndarray, fars: list[float]):
    total = impostor_hist.sum()
    # tail[k] = number of impostors with score >= bin k
    tail = np.cumsum(impostor_hist[::-1])[::-1]
    edges = np.arange(4001) * 0.0005 - 1.0
    out = {}
    for far in fars:
        allowed = far * total
        k = int(np.argmax(tail <= allowed))
        th = float(edges[k])
        out[far] = {"threshold": round(th, 4), "tar": float(np.mean(genuine >= th)), "impostors_observed": int(tail[k])}
    return out, int(total)


def eer(genuine: np.ndarray, impostor_hist: np.ndarray) -> float:
    total = impostor_hist.sum()
    tail = np.cumsum(impostor_hist[::-1])[::-1] / total
    edges = np.arange(4001) * 0.0005 - 1.0
    frr = np.array([np.mean(genuine < t) for t in edges[::4]])
    far = tail[::4]
    k = int(np.argmin(np.abs(frr - far)))
    return float((frr[k] + far[k]) / 2)


def attendance_simulation(x, people, cal: SimilarityCalibration, margins=(0.0, 0.08), enroll_per_person=1, seed=0):
    rng = np.random.default_rng(seed)
    by_person = defaultdict(list)
    for i, p in enumerate(people):
        by_person[p].append(i)
    employees = {p: idx for p, idx in by_person.items() if len(idx) > enroll_per_person}
    strangers = [idx[0] for p, idx in by_person.items() if len(idx) == 1]

    gallery_idx, gallery_owner, probes = [], [], []
    for p, idx in employees.items():
        idx = list(idx)
        rng.shuffle(idx)
        for g in idx[:enroll_per_person]:
            gallery_idx.append(g)
            gallery_owner.append(p)
        probes += [(i, p) for i in idx[enroll_per_person:]]
    owners = np.array(gallery_owner)
    G = x[np.array(gallery_idx)]

    def rank(q):
        s = G @ q
        order = np.argsort(-s)[:50]
        best = order[0]
        rival = next((s[j] for j in order[1:] if owners[j] != owners[best]), -1.0)
        return owners[best], float(s[best]), float(rival)

    gen = [(truth, *rank(x[i])) for i, truth in probes]
    imp = [rank(x[i]) for i in strangers]
    results = []
    for margin in margins:
        for sim_th in (70, 80, 90, 95, 99):
            th = cal.to_cosine(sim_th)
            correct = wrong = rejected = 0
            for truth, who, s, rival in gen:
                accept = s >= th and (s - rival >= margin or margin == 0.0)
                if not accept:
                    rejected += 1
                elif who == truth:
                    correct += 1
                else:
                    wrong += 1
            let_in = sum(1 for who, s, rival in imp if s >= th and (s - rival >= margin or margin == 0.0))
            n_g, n_i = len(gen), len(imp)
            results.append(
                {
                    "margin": margin,
                    "threshold_similarity": sim_th,
                    "threshold_cosine": round(th, 4),
                    "employees_enrolled": len(employees),
                    "checkins": n_g,
                    "strangers": n_i,
                    "correct_checkin_rate": correct / n_g,
                    "wrong_person_rate": wrong / n_g,
                    "false_reject_rate": rejected / n_g,
                    "stranger_accept_rate": let_in / n_i,
                    "overall_decision_accuracy": (correct + (n_i - let_in)) / (n_g + n_i),
                }
            )
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emb", type=Path, required=True)
    ap.add_argument("--pairs", type=Path, help="LFW pairs.txt; omit for your own photo folders")
    ap.add_argument("--variant", choices=["plain", "flip"], default="flip")
    ap.add_argument("--calibration-out", type=Path)
    ap.add_argument("--report", type=Path, default=Path("reports/lfw_benchmark.json"))
    args = ap.parse_args()

    names, people, x, raw = load(args.emb, args.variant)
    index = {n: i for i, n in enumerate(names)}
    report: dict = {
        "dataset": "LFW (Labeled Faces in the Wild), 13,233 images / 5,749 people",
        "embedding_variant": args.variant,
        "images_embedded": len(names),
        "images_without_detected_face": int(len(raw["missing"])),
    }

    if args.pairs:
        pairs = lfw_pairs(args.pairs, index)
        ps = np.array([float(x[a] @ x[b]) for a, b, _ in pairs])
        pl = np.array([s for _, _, s in pairs])
        acc, sd, th = ten_fold_accuracy(ps, pl)
        report["lfw_10fold"] = {"pairs": len(pairs), "accuracy": acc, "std": sd, "mean_threshold": th}
        print(f"LFW 10-fold verification accuracy: {acc * 100:.2f}% +- {sd * 100:.2f} ({len(pairs)} pairs)")

    genuine, imp_hist, imp_top = all_pair_scores(x, people)
    fars = [1e-2, 1e-3, 1e-4, 1e-5, 1e-6]
    tars, n_imp = tar_at_far(genuine, imp_hist, fars)
    report["roc"] = {
        "genuine_pairs": int(len(genuine)),
        "impostor_pairs": n_imp,
        "eer": eer(genuine, imp_hist),
        "tar_at_far": {f"{k:g}": v for k, v in tars.items()},
        "genuine_median": float(np.median(genuine)),
    }
    print(f"All pairs: {len(genuine):,} genuine / {n_imp:,} impostor, EER {report['roc']['eer'] * 100:.2f}%")
    for k, v in tars.items():
        print(f"  TAR @ FAR {k:g}: {v['tar'] * 100:.2f}%  (cosine >= {v['threshold']})")

    # Calibration from the impostor distribution (reconstructed from histogram + exact top scores).
    centers = np.arange(4001) * 0.0005 - 1.0
    low = np.repeat(centers[centers <= 0.25], imp_hist[centers <= 0.25])
    imp_scores = np.concatenate([low, imp_top])
    cos = fit_from_impostors(imp_scores)
    cal = SimilarityCalibration(cos, source="lfw")
    report["calibration"] = cal.describe()
    if args.calibration_out:
        args.calibration_out.write_text(
            json.dumps(
                {
                    "model": str(args.emb.name),
                    "variant": args.variant,
                    "anchors_similarity": ANCHOR_SIMILARITIES,
                    "anchors_far": ANCHOR_FARS,
                    "cosines": [round(float(c), 5) for c in cal.cosines],
                    "source": "LFW all-pairs impostor distribution",
                },
                indent=2,
            )
        )
        print(f"calibration written to {args.calibration_out}")
    sims = cal.to_similarity(genuine)
    report["genuine_similarity_distribution"] = {
        "p01": float(np.percentile(sims, 1)),
        "p05": float(np.percentile(sims, 5)),
        "median": float(np.median(sims)),
        "share_at_or_above_99": float(np.mean(sims >= 99)),
        "share_at_or_above_90": float(np.mean(sims >= 90)),
    }

    sim = attendance_simulation(x, people, cal)
    report["attendance_simulation"] = sim
    print("\nAttendance simulation (1 enrolment photo per employee):")
    print(f"  {'margin':>6} {'thr':>4} {'correct':>8} {'wrong':>7} {'reject':>7} {'stranger':>8} {'overall':>8}")
    for r in sim:
        print(
            f"  {r['margin']:>6.2f} {r['threshold_similarity']:>4} {r['correct_checkin_rate'] * 100:>7.2f}% {r['wrong_person_rate'] * 100:>6.3f}% "
            f"{r['false_reject_rate'] * 100:>6.2f}% {r['stranger_accept_rate'] * 100:>7.3f}% {r['overall_decision_accuracy'] * 100:>7.2f}%"
        )
    report["liveness_on_real_photos"] = {
        "note": "LFW photos are real (bona fide) faces; share judged live is the passive model's acceptance of genuine users",
        "share_live_at_0.5": float(np.mean(raw["liveness"] >= 0.5)),
        "median_score": float(np.median(raw["liveness"])),
    }
    report["engine_ms_per_image"] = {"median": float(np.median(raw["ms"])), "p95": float(np.percentile(raw["ms"], 95))}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))
    print(f"\nreport written to {args.report}")


if __name__ == "__main__":
    main()
