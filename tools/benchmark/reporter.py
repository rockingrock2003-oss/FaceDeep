from __future__ import annotations

import csv
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.benchmark.manifest import BenchmarkManifest
from tools.benchmark.metrics import (
    LatencyPercentiles,
    LivenessMetrics,
    ProbeEvaluationResult,
    RecognitionMetrics,
)
from tools.benchmark.profiler import ResourceSummary

try:
    from tabulate import tabulate
    _HAS_TABULATE = True
except ImportError:
    _HAS_TABULATE = False


def _format_table(rows: list[list[Any]], headers: list[str]) -> str:
    """Format table using tabulate or simple text alignment fallback."""
    if _HAS_TABULATE:
        return tabulate(rows, headers=headers, tablefmt="github")

    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val)))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-|-".join("-" * col_widths[i] for i in range(len(headers)))
    data_lines = [
        " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        for row in rows
    ]
    return f"| {header_line} |\n| {sep_line} |\n" + "\n".join(f"| {l} |" for l in data_lines)


class BenchmarkReporter:
    """Handles generating machine-readable (JSON/CSV) and human-readable (Markdown/Console) reports."""

    def __init__(
        self,
        output_dir: Path | str,
        manifest: BenchmarkManifest,
        results: list[ProbeEvaluationResult],
        recognition_metrics: RecognitionMetrics,
        liveness_metrics: LivenessMetrics,
        overall_latency: LatencyPercentiles,
        subsystem_latencies: dict[str, LatencyPercentiles],
        resource_summary: ResourceSummary,
        similarity_threshold: float,
        liveness_threshold: float,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = manifest
        self.results = results
        self.rec_metrics = recognition_metrics
        self.live_metrics = liveness_metrics
        self.latency = overall_latency
        self.subsystem_latencies = subsystem_latencies
        self.resources = resource_summary
        self.similarity_threshold = similarity_threshold
        self.liveness_threshold = liveness_threshold
        self.timestamp = datetime.now(UTC).isoformat()

    def build_report_dict(self) -> dict[str, Any]:
        """Build structured dictionary for JSON export."""
        return {
            "title": "FaceDeep On-Premise Benchmark Report",
            "version": "1.0.0",
            "timestamp_utc": self.timestamp,
            "environment": {
                "os": platform.platform(),
                "python_version": platform.python_version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            },
            "parameters": {
                "similarity_threshold": self.similarity_threshold,
                "liveness_min_score": self.liveness_threshold,
                "manifest_name": self.manifest.name,
                "gallery_size": self.manifest.total_gallery,
                "total_probes": self.manifest.total_probes,
            },
            "recognition": self.rec_metrics.to_dict(),
            "liveness": self.live_metrics.to_dict(),
            "latency": {
                "overall": self.latency.to_dict(),
                "subsystems": {
                    k: v.to_dict() for k, v in self.subsystem_latencies.items()
                },
            },
            "resources": self.resources.to_dict(),
            "pass_fail_summary": {
                "latency_p95_under_2s": self.latency.p95 <= 2000.0,
                "cpu_peak_under_70pct": self.resources.cpu_peak_percent <= 70.0,
                "ram_peak_under_3500mb": self.resources.ram_peak_mb <= 3500.0,
            },
            "events": [r.to_dict() for r in self.results],
        }

    def save_json(self, filename: str = "results.json") -> Path:
        target = self.output_dir / filename
        data = self.build_report_dict()
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return target

    def save_csv(self, filename: str = "events.csv") -> Path:
        target = self.output_dir / filename
        fieldnames = [
            "probe_id",
            "true_identity",
            "is_live_ground_truth",
            "attack_type",
            "status",
            "liveness_score",
            "liveness_passed",
            "matched_identity",
            "similarity",
            "is_match_above_threshold",
            "rank1_correct",
            "latency_total_ms",
            "error_message",
        ]
        with open(target, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in self.results:
                row = r.to_dict()
                row.pop("latency_breakdown_ms", None)
                writer.writerow(row)
        return target

    def generate_markdown(self, filename: str = "summary.md") -> Path:
        target = self.output_dir / filename
        data = self.build_report_dict()

        # Tables
        rec_table = _format_table(
            [
                ["True Accept Rate (TAR)", f"{self.rec_metrics.tar_percent}%", ">= 99.0% (target)"],
                ["False Accept Rate (FAR)", f"{self.rec_metrics.far_percent}%", "<= 0.1% (target)"],
                ["False Reject Rate (FRR)", f"{self.rec_metrics.frr_percent}%", "<= 1.0% (target)"],
                ["Rank-1 Accuracy", f"{self.rec_metrics.rank1_accuracy_percent}%", ">= 99.0% (target)"],
                ["Genuine Probes Tested", str(self.rec_metrics.total_genuine_probes), "-"],
                ["Impostor Probes Tested", str(self.rec_metrics.total_impostor_probes), "-"],
            ],
            headers=["Biometric Metric", "Measured Value", "Acceptance Criterion"],
        )

        pad_table = _format_table(
            [
                ["APCER (Overall)", f"{self.live_metrics.apcer_percent}%", "<= 1.0%"],
                ["BPCER (Live Reject)", f"{self.live_metrics.bpcer_percent}%", "<= 2.0%"],
                ["ACER (Average Error)", f"{self.live_metrics.acer_percent}%", "<= 1.5%"],
                ["Bona Fide Live Tests", str(self.live_metrics.total_bona_fide), "-"],
                ["Attack Tests", str(self.live_metrics.total_attacks), "-"],
            ],
            headers=["PAD Metric (ISO/IEC 30107-3)", "Measured Value", "Target"],
        )

        lat_table = _format_table(
            [
                ["p50 (Median)", f"{self.latency.p50:.1f} ms", "<= 800 ms"],
                ["p90", f"{self.latency.p90:.1f} ms", "-"],
                ["p95", f"{self.latency.p95:.1f} ms", "<= 2000 ms (Hard Limit)"],
                ["p99", f"{self.latency.p99:.1f} ms", "<= 2500 ms"],
                ["Mean Latency", f"{self.latency.mean:.1f} ms", "-"],
            ],
            headers=["Latency Percentile", "Measured Duration", "SLA Target"],
        )

        res_table = _format_table(
            [
                ["CPU Average Utilization", f"{self.resources.cpu_average_percent:.1f}%", "<= 45%"],
                ["CPU Peak Utilization", f"{self.resources.cpu_peak_percent:.1f}%", "<= 70%"],
                ["RAM Baseline RSS", f"{self.resources.ram_baseline_mb:.1f} MB", "-"],
                ["RAM Peak RSS", f"{self.resources.ram_peak_mb:.1f} MB", "<= 3500 MB"],
                ["RAM Delta", f"{self.resources.ram_delta_mb:.1f} MB", "-"],
                ["GPU Acceleration", self.resources.gpu_device_name or "N/A (CPU Execution)", "Optional"],
            ],
            headers=["System Resource", "Measured Value", "Envelope Limit"],
        )

        status_badge = "PASS" if self.latency.p95 <= 2000.0 else "FAIL"

        md_content = f"""# FaceDeep On-Premise Prototype: Benchmark Summary Report

**Execution Timestamp:** `{self.timestamp}`  
**Dataset Manifest:** `{self.manifest.name}` (Gallery: {self.manifest.total_gallery}, Probes: {self.manifest.total_probes})  
**Operating Thresholds:** Similarity $\\tau = {self.similarity_threshold}$, Liveness Score $\\ge {self.liveness_threshold}$  
**Overall Status:** **`{status_badge}`**

---

## 1. Biometric Recognition Performance

{rec_table}

---

## 2. Presentation Attack Detection (Liveness)

{pad_table}

---

## 3. Latency Distribution & Subsystem Benchmarks

{lat_table}

---

## 4. Hardware & Resource Consumption

{res_table}

---
*Report auto-generated by `tools/benchmark/runner.py`*
"""
        with open(target, "w", encoding="utf-8") as f:
            f.write(md_content)
        return target

    def print_terminal_summary(self) -> None:
        """Print concise, human-readable summary table to stdout."""
        print("\n" + "=" * 70)
        print("          FACEDEEP ON-PREMISE PROTOTYPE BENCHMARK SUMMARY")
        print("=" * 70)
        print(f"Manifest: {self.manifest.name} | Gallery: {self.manifest.total_gallery} | Probes: {self.manifest.total_probes}")
        print(f"Threshold: tau={self.similarity_threshold} | Liveness Min Score: {self.liveness_threshold}")
        print("-" * 70)
        
        print(f"BIOMETRIC RECOGNITION:")
        print(f"  * TAR (Genuine Match Rate):  {self.rec_metrics.tar_percent:.2f}%  (target >= 99.0%)")
        print(f"  * FAR (Impostor Match Rate): {self.rec_metrics.far_percent:.2f}%  (target <= 0.1%)")
        print(f"  * Rank-1 Accuracy:          {self.rec_metrics.rank1_accuracy_percent:.2f}%")
        print("-" * 70)

        print(f"PRESENTATION ATTACK DETECTION (LIVENESS):")
        print(f"  * APCER (Attack Pass Rate):  {self.live_metrics.apcer_percent:.2f}%  (target <= 1.0%)")
        print(f"  * BPCER (Live Reject Rate):  {self.live_metrics.bpcer_percent:.2f}%  (target <= 2.0%)")
        print(f"  * ACER (Average Error):      {self.live_metrics.acer_percent:.2f}%")
        print("-" * 70)

        p95_pass = "PASS" if self.latency.p95 <= 2000.0 else "FAIL"
        print(f"LATENCY & PERFORMANCE:")
        print(f"  * p50 (Median):              {self.latency.p50:.1f} ms")
        print(f"  * p95 (95th Percentile):     {self.latency.p95:.1f} ms  [{p95_pass} (target <= 2000 ms)]")
        print(f"  * p99 (99th Percentile):     {self.latency.p99:.1f} ms")
        print(f"  * Mean Latency:              {self.latency.mean:.1f} ms")
        print("-" * 70)

        print(f"RESOURCE UTILIZATION:")
        print(f"  * CPU Utilization (Avg/Peak): {self.resources.cpu_average_percent:.1f}% / {self.resources.cpu_peak_percent:.1f}%")
        print(f"  * RAM Peak RSS:               {self.resources.ram_peak_mb:.1f} MB (baseline: {self.resources.ram_baseline_mb:.1f} MB)")
        gpu_str = self.resources.gpu_device_name or "N/A (CPU Execution Provider)"
        print(f"  * GPU Device:                 {gpu_str}")
        print("=" * 70 + "\n")
