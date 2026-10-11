from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.services.embedding_store import EmbeddingStore
from app.services.face_recognition import get_face_service
from app.services.liveness import LivenessDetector
from tools.benchmark.manifest import BenchmarkManifest, load_manifest
from tools.benchmark.metrics import ProbeEvaluationResult, compute_metrics
from tools.benchmark.profiler import ResourceProfiler
from tools.benchmark.reporter import BenchmarkReporter


def warmup_models(face_service, liveness_detector) -> None:
    """Warm up ONNX / InsightFace execution graphs to eliminate cold-start spikes."""
    blank = np.zeros((640, 640, 3), dtype=np.uint8)
    cv2.circle(blank, (320, 280), 120, (180, 150, 130), -1)
    _, buf = cv2.imencode(".jpg", blank)
    b_bytes = buf.tobytes()

    try:
        liveness_detector.check_liveness_sync(b_bytes)
    except Exception:
        pass

    try:
        face_service.extract_embedding_sync(b_bytes)
    except Exception:
        pass


def run_benchmark(
    manifest_path: str | Path,
    similarity_threshold: float = 0.40,
    liveness_threshold: float = 70.0,
    output_dir: str | Path = "tools/benchmark/results",
    warmup: bool = True,
    verbose: bool = True,
) -> int:
    """Execute complete reproducible benchmark run.

    Returns:
        0 on success, non-zero on failure.
    """
    manifest_path = Path(manifest_path).resolve()
    output_dir = Path(output_dir).resolve()

    if verbose:
        print(f"[Benchmark] Loading dataset manifest: {manifest_path}")

    try:
        manifest = load_manifest(manifest_path, validate_files=False)
    except Exception as exc:
        print(f"[Error] Failed to load manifest: {exc}", file=sys.stderr)
        return 1

    if verbose:
        print(f"[Benchmark] Manifest '{manifest.name}' loaded: {manifest.total_gallery} gallery items, {manifest.total_probes} probes.")

    # Initialize services
    if verbose:
        print("[Benchmark] Initializing FaceDeep biometric models and vector store...")
    face_service = get_face_service()
    liveness_detector = LivenessDetector()
    embedding_store = EmbeddingStore()

    if warmup:
        if verbose:
            print("[Benchmark] Warming up inference graph sessions...")
        warmup_models(face_service, liveness_detector)

    # Use unique isolated namespace for benchmark gallery
    benchmark_namespace = f"bench_{uuid.uuid4().hex[:12]}"

    # Phase 1: Enrollment
    if verbose:
        print(f"[Benchmark] Phase 1/2: Enrolling {manifest.total_gallery} gallery reference identities...")

    enrolled_count = 0
    for record in manifest.gallery:
        if not record.image_path.is_file():
            print(f"[Error] Missing gallery image for {record.person_id}: {record.image_path}", file=sys.stderr)
            return 1

        with open(record.image_path, "rb") as f:
            img_bytes = f.read()

        try:
            embedding, _ = face_service.extract_embedding_sync(img_bytes)
            face_id = f"{record.person_id}_{uuid.uuid4().hex[:8]}"
            embedding_store.add_embedding(
                user_id=benchmark_namespace,
                face_id=face_id,
                embedding=embedding,
                person_id=record.person_id,
            )
            enrolled_count += 1
            if verbose:
                print(f"  + Enrolled {record.person_id} ({record.image_path.name})")
        except Exception as exc:
            print(f"[Error] Failed enrolling {record.person_id}: {exc}", file=sys.stderr)
            return 1

    if verbose:
        print(f"[Benchmark] Successfully enrolled {enrolled_count} references into namespace '{benchmark_namespace}'.")

    # Phase 2: Probe Evaluation with Resource Profiling
    if verbose:
        print(f"[Benchmark] Phase 2/2: Evaluating {manifest.total_probes} probe presentations...")

    profiler = ResourceProfiler(sample_interval_sec=0.05)
    profiler.start()

    results: list[ProbeEvaluationResult] = []

    try:
        for idx, probe in enumerate(manifest.probes, start=1):
            t0 = time.perf_counter_ns()
            breakdown: dict[str, float] = {}

            if not probe.image_path.is_file():
                results.append(
                    ProbeEvaluationResult(
                        probe_id=probe.probe_id,
                        true_identity=probe.expected_identity,
                        is_live_ground_truth=probe.is_live,
                        attack_type=probe.attack_type,
                        status="error",
                        liveness_score=0.0,
                        liveness_passed=False,
                        matched_identity=None,
                        similarity=0.0,
                        is_match_above_threshold=False,
                        rank1_correct=False,
                        latency_total_ms=0.0,
                        error_message=f"Sample file not found: {probe.image_path}",
                    )
                )
                continue

            with open(probe.image_path, "rb") as f:
                probe_bytes = f.read()

            t_read = time.perf_counter_ns()
            breakdown["io_read_ms"] = (t_read - t0) / 1_000_000

            # 1. Evaluate Liveness
            t_live_start = time.perf_counter_ns()
            try:
                live_res = liveness_detector.check_liveness_sync(probe_bytes)
                live_score = float(live_res.get("liveness_score", 0.0))
                live_passed = (live_res.get("status") == "passed") and (live_score >= liveness_threshold)
            except Exception as exc:
                live_score = 0.0
                live_passed = False
            t_live_end = time.perf_counter_ns()
            breakdown["liveness_inference_ms"] = (t_live_end - t_live_start) / 1_000_000

            # 2. Extract Embedding
            t_emb_start = time.perf_counter_ns()
            embedding = None
            emb_error = None
            try:
                embedding, _ = face_service.extract_embedding_sync(probe_bytes)
            except Exception as exc:
                emb_error = str(exc)
            t_emb_end = time.perf_counter_ns()
            breakdown["embedding_extraction_ms"] = (t_emb_end - t_emb_start) / 1_000_000

            # 3. Vector Match Search
            t_search_start = time.perf_counter_ns()
            matches = []
            if embedding is not None:
                matches = embedding_store.search(
                    user_id=benchmark_namespace,
                    query_embedding=embedding,
                    n_results=1,
                )
            t_search_end = time.perf_counter_ns()
            breakdown["vector_search_ms"] = (t_search_end - t_search_start) / 1_000_000

            t_total_ms = (time.perf_counter_ns() - t0) / 1_000_000

            # Classify result
            top_match = matches[0] if matches else None
            matched_id = top_match["person_id"] if top_match else None
            top_sim = float(top_match["similarity"]) if top_match else 0.0
            is_above_thresh = (top_sim >= similarity_threshold)

            # Rank-1 check
            is_rank1_correct = False
            if probe.expected_identity is not None and matched_id == probe.expected_identity:
                is_rank1_correct = True

            # Determine transaction outcome status
            if emb_error and not live_passed:
                status = "spoof_rejected"
            elif emb_error:
                status = "error"
            elif not live_passed:
                status = "spoof_rejected"
            elif is_above_thresh and is_rank1_correct:
                status = "verified"
            elif is_above_thresh and not is_rank1_correct:
                status = "false_accept"
            else:
                status = "unrecognized"

            result = ProbeEvaluationResult(
                probe_id=probe.probe_id,
                true_identity=probe.expected_identity,
                is_live_ground_truth=probe.is_live,
                attack_type=probe.attack_type,
                status=status,
                liveness_score=live_score,
                liveness_passed=live_passed,
                matched_identity=matched_id,
                similarity=top_sim,
                is_match_above_threshold=is_above_thresh,
                rank1_correct=is_rank1_correct,
                latency_total_ms=t_total_ms,
                latency_breakdown_ms=breakdown,
                error_message=emb_error,
            )
            results.append(result)

            if verbose:
                tag = f"[{idx}/{manifest.total_probes}]"
                print(
                    f"  {tag} {probe.probe_id.ljust(15)} | Live: {str(live_passed).ljust(5)} (score={live_score:5.1f}) | Match: {str(matched_id or 'None').ljust(12)} (sim={top_sim:.3f}) | Status: {status.ljust(14)} | {t_total_ms:6.1f}ms"
                )

    finally:
        resource_summary = profiler.stop()

        # Clean up temporary benchmark ChromaDB collection
        try:
            coll = embedding_store.get_or_create_collection(benchmark_namespace)
            embedding_store.client.delete_collection(coll.name)
        except Exception:
            pass

    # Phase 3: Compute Metrics & Generate Reports
    rec_metrics, live_metrics, latency_stats, subsystem_latencies = compute_metrics(
        results=results,
        similarity_threshold=similarity_threshold,
        liveness_threshold=liveness_threshold,
    )

    reporter = BenchmarkReporter(
        output_dir=output_dir,
        manifest=manifest,
        results=results,
        recognition_metrics=rec_metrics,
        liveness_metrics=live_metrics,
        overall_latency=latency_stats,
        subsystem_latencies=subsystem_latencies,
        resource_summary=resource_summary,
        similarity_threshold=similarity_threshold,
        liveness_threshold=liveness_threshold,
    )

    json_path = reporter.save_json("results.json")
    csv_path = reporter.save_csv("events.csv")
    md_path = reporter.generate_markdown("summary.md")

    reporter.print_terminal_summary()

    print(f"[Benchmark] Report artifacts written to {output_dir}:")
    print(f"  * JSON:     {json_path}")
    print(f"  * CSV:      {csv_path}")
    print(f"  * Markdown: {md_path}\n")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FaceDeep On-Premise Reproducible Benchmark Harness",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    default_manifest = Path(__file__).parent / "fixtures" / "manifest.json"
    default_out = Path(__file__).parent / "results"

    parser.add_argument(
        "--manifest",
        type=str,
        default=str(default_manifest),
        help="Path to dataset manifest JSON or CSV file",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=settings.FACE_RECOGNITION_THRESHOLD,
        help="Cosine similarity threshold for face identification",
    )
    parser.add_argument(
        "--liveness-threshold",
        type=float,
        default=settings.LIVENESS_MIN_SCORE,
        help="Minimum liveness score (0-100) to pass presentation attack detection",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(default_out),
        help="Directory where machine-readable JSON/CSV and markdown reports will be written",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Disable model inference graph warm-up prior to benchmark timing",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-probe live terminal logs",
    )

    args = parser.parse_args()

    exit_code = run_benchmark(
        manifest_path=args.manifest,
        similarity_threshold=args.threshold,
        liveness_threshold=args.liveness_threshold,
        output_dir=args.output_dir,
        warmup=not args.no_warmup,
        verbose=not args.quiet,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
