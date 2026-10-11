from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class ProbeEvaluationResult:
    probe_id: str
    true_identity: str | None
    is_live_ground_truth: bool
    attack_type: str | None
    status: str  # "verified", "unrecognized", "spoof_rejected", "error"
    liveness_score: float
    liveness_passed: bool
    matched_identity: str | None
    similarity: float
    is_match_above_threshold: bool
    rank1_correct: bool
    latency_total_ms: float
    latency_breakdown_ms: dict[str, float] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "true_identity": self.true_identity,
            "is_live_ground_truth": self.is_live_ground_truth,
            "attack_type": self.attack_type,
            "status": self.status,
            "liveness_score": round(self.liveness_score, 2),
            "liveness_passed": self.liveness_passed,
            "matched_identity": self.matched_identity,
            "similarity": round(self.similarity, 4),
            "is_match_above_threshold": self.is_match_above_threshold,
            "rank1_correct": self.rank1_correct,
            "latency_total_ms": round(self.latency_total_ms, 2),
            "latency_breakdown_ms": {
                k: round(v, 2) for k, v in self.latency_breakdown_ms.items()
            },
            "error_message": self.error_message,
        }


@dataclass
class LatencyPercentiles:
    p50: float
    p90: float
    p95: float
    p99: float
    mean: float
    min: float
    max: float
    std_dev: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "p50_ms": round(self.p50, 2),
            "p90_ms": round(self.p90, 2),
            "p95_ms": round(self.p95, 2),
            "p99_ms": round(self.p99, 2),
            "mean_ms": round(self.mean, 2),
            "min_ms": round(self.min, 2),
            "max_ms": round(self.max, 2),
            "std_dev_ms": round(self.std_dev, 2),
        }


@dataclass
class RecognitionMetrics:
    total_genuine_probes: int
    true_accepts: int
    false_rejects: int
    tar_percent: float
    frr_percent: float
    total_impostor_probes: int
    true_rejects: int
    false_accepts: int
    far_percent: float
    rank1_accuracy_percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_genuine_probes": self.total_genuine_probes,
            "true_accepts": self.true_accepts,
            "false_rejects": self.false_rejects,
            "tar_percent": round(self.tar_percent, 2),
            "frr_percent": round(self.frr_percent, 2),
            "total_impostor_probes": self.total_impostor_probes,
            "true_rejects": self.true_rejects,
            "false_accepts": self.false_accepts,
            "far_percent": round(self.far_percent, 2),
            "rank1_accuracy_percent": round(self.rank1_accuracy_percent, 2),
        }


@dataclass
class LivenessMetrics:
    total_bona_fide: int
    bona_fide_passed: int
    bona_fide_failed: int
    bpcer_percent: float
    total_attacks: int
    attacks_blocked: int
    attacks_passed: int
    apcer_percent: float
    apcer_by_attack_type: dict[str, float]
    acer_percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_bona_fide": self.total_bona_fide,
            "bona_fide_passed": self.bona_fide_passed,
            "bona_fide_failed": self.bona_fide_failed,
            "bpcer_percent": round(self.bpcer_percent, 2),
            "total_attacks": self.total_attacks,
            "attacks_blocked": self.attacks_blocked,
            "attacks_passed": self.attacks_passed,
            "apcer_percent": round(self.apcer_percent, 2),
            "apcer_by_attack_type": {
                k: round(v, 2) for k, v in self.apcer_by_attack_type.items()
            },
            "acer_percent": round(self.acer_percent, 2),
        }


def compute_latency_percentiles(latencies_ms: list[float]) -> LatencyPercentiles:
    """Compute distribution statistics for a list of latency readings."""
    if not latencies_ms:
        return LatencyPercentiles(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    arr = np.array(latencies_ms, dtype=np.float64)
    return LatencyPercentiles(
        p50=float(np.percentile(arr, 50)),
        p90=float(np.percentile(arr, 90)),
        p95=float(np.percentile(arr, 95)),
        p99=float(np.percentile(arr, 99)),
        mean=float(np.mean(arr)),
        min=float(np.min(arr)),
        max=float(np.max(arr)),
        std_dev=float(np.std(arr)),
    )


def compute_metrics(
    results: list[ProbeEvaluationResult],
    similarity_threshold: float,
    liveness_threshold: float,
) -> tuple[RecognitionMetrics, LivenessMetrics, LatencyPercentiles, dict[str, LatencyPercentiles]]:
    """Compute all biometric, liveness, and latency metrics from raw probe evaluations."""
    # 1. Biometric Recognition Metrics
    genuine_results = [
        r for r in results if r.is_live_ground_truth and r.true_identity is not None and r.status != "error"
    ]
    impostor_results = [
        r for r in results if r.is_live_ground_truth and r.true_identity is None and r.status != "error"
    ]

    # Genuine
    true_accepts = sum(1 for r in genuine_results if r.is_match_above_threshold and r.rank1_correct)
    false_rejects = len(genuine_results) - true_accepts
    tar = (true_accepts / len(genuine_results) * 100.0) if genuine_results else 0.0
    frr = (false_rejects / len(genuine_results) * 100.0) if genuine_results else 0.0

    # Impostors
    false_accepts = sum(1 for r in impostor_results if r.is_match_above_threshold)
    true_rejects = len(impostor_results) - false_accepts
    far = (false_accepts / len(impostor_results) * 100.0) if impostor_results else 0.0

    # Rank-1 closed-set accuracy
    rank1_correct_count = sum(1 for r in genuine_results if r.rank1_correct)
    rank1_acc = (rank1_correct_count / len(genuine_results) * 100.0) if genuine_results else 0.0

    rec_metrics = RecognitionMetrics(
        total_genuine_probes=len(genuine_results),
        true_accepts=true_accepts,
        false_rejects=false_rejects,
        tar_percent=tar,
        frr_percent=frr,
        total_impostor_probes=len(impostor_results),
        true_rejects=true_rejects,
        false_accepts=false_accepts,
        far_percent=far,
        rank1_accuracy_percent=rank1_acc,
    )

    # 2. Presentation Attack Detection (Liveness) Metrics
    bona_fide = [r for r in results if r.is_live_ground_truth and r.status != "error"]
    attacks = [r for r in results if not r.is_live_ground_truth and r.status != "error"]

    bona_fide_passed = sum(1 for r in bona_fide if r.liveness_passed)
    bona_fide_failed = len(bona_fide) - bona_fide_passed
    bpcer = (bona_fide_failed / len(bona_fide) * 100.0) if bona_fide else 0.0

    attacks_passed = sum(1 for r in attacks if r.liveness_passed)
    attacks_blocked = len(attacks) - attacks_passed
    apcer = (attacks_passed / len(attacks) * 100.0) if attacks else 0.0

    # APCER per attack species
    apcer_by_type: dict[str, float] = {}
    attack_species = set(r.attack_type or "unspecified" for r in attacks)
    for sp in attack_species:
        sp_attacks = [r for r in attacks if (r.attack_type or "unspecified") == sp]
        sp_passed = sum(1 for r in sp_attacks if r.liveness_passed)
        apcer_by_type[sp] = (sp_passed / len(sp_attacks) * 100.0) if sp_attacks else 0.0

    worst_apcer = max(apcer_by_type.values()) if apcer_by_type else apcer
    acer = (worst_apcer + bpcer) / 2.0

    live_metrics = LivenessMetrics(
        total_bona_fide=len(bona_fide),
        bona_fide_passed=bona_fide_passed,
        bona_fide_failed=bona_fide_failed,
        bpcer_percent=bpcer,
        total_attacks=len(attacks),
        attacks_blocked=attacks_blocked,
        attacks_passed=attacks_passed,
        apcer_percent=apcer,
        apcer_by_attack_type=apcer_by_type,
        acer_percent=acer,
    )

    # 3. Latency Percentiles
    valid_results = [r for r in results if r.status != "error"]
    total_latencies = [r.latency_total_ms for r in valid_results]
    overall_latency = compute_latency_percentiles(total_latencies)

    # Breakdown latencies
    breakdown_keys = set()
    for r in valid_results:
        breakdown_keys.update(r.latency_breakdown_ms.keys())

    subsystem_latencies: dict[str, LatencyPercentiles] = {}
    for k in sorted(breakdown_keys):
        k_vals = [r.latency_breakdown_ms[k] for r in valid_results if k in r.latency_breakdown_ms]
        subsystem_latencies[k] = compute_latency_percentiles(k_vals)

    return rec_metrics, live_metrics, overall_latency, subsystem_latencies
