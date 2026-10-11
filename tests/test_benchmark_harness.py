import json
from pathlib import Path

import pytest

from tools.benchmark.fixtures.generate_fixtures import main as generate_fixtures
from tools.benchmark.manifest import (
    ManifestValidationError,
    SampleNotFoundError,
    load_manifest,
)
from tools.benchmark.metrics import (
    ProbeEvaluationResult,
    compute_latency_percentiles,
    compute_metrics,
)
from tools.benchmark.profiler import ResourceProfiler
from tools.benchmark.runner import run_benchmark

FIXTURES_MANIFEST = (
    Path(__file__).resolve().parent.parent / "tools" / "benchmark" / "fixtures" / "manifest.json"
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_fixture_dataset():
    """Generate local face fixtures at test time; never store biometric images in git."""
    generate_fixtures()


def test_manifest_load_valid():
    """Verify that the default fixture manifest loads properly."""
    assert FIXTURES_MANIFEST.is_file(), f"Missing fixture manifest at {FIXTURES_MANIFEST}"
    manifest = load_manifest(FIXTURES_MANIFEST, validate_files=True)
    assert manifest.name == "FaceDeep-Local-Fixture-v1"
    assert manifest.total_gallery == 2
    assert manifest.total_probes == 5
    assert len(manifest.genuine_probes) == 2
    assert len(manifest.impostor_probes) == 2  # 1 live impostor + 1 corrupt probe with is_live=True
    assert len(manifest.spoof_probes) == 1


def test_manifest_missing_file_fails_clearly(tmp_path):
    """Verify that referencing non-existent files raises clear SampleNotFoundError."""
    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text(
        json.dumps(
            {
                "name": "BadManifest",
                "gallery": [
                    {"person_id": "EMP_GHOST", "image_path": "non_existent_gallery_img.jpg"}
                ],
                "probes": [],
            }
        )
    )

    with pytest.raises(SampleNotFoundError) as exc_info:
        load_manifest(bad_manifest, validate_files=True)

    assert "EMP_GHOST" in str(exc_info.value)
    assert "not found at" in str(exc_info.value)


def test_manifest_invalid_syntax_fails_clearly(tmp_path):
    """Verify that invalid JSON syntax fails clearly."""
    corrupt_json = tmp_path / "corrupt.json"
    corrupt_json.write_text("{ this is not json }")

    with pytest.raises(ManifestValidationError) as exc_info:
        load_manifest(corrupt_json)

    assert "Invalid JSON syntax" in str(exc_info.value)


def test_manifest_missing_required_fields_fails_clearly(tmp_path):
    """Verify that missing required fields like person_id raises ManifestValidationError."""
    missing_fields = tmp_path / "missing_fields.json"
    missing_fields.write_text(
        json.dumps(
            {
                "gallery": [{"image_path": "some_image.jpg"}],  # missing person_id
                "probes": [],
            }
        )
    )

    with pytest.raises(ManifestValidationError) as exc_info:
        load_manifest(missing_fields)

    assert "missing required 'person_id'" in str(exc_info.value)


def test_resource_profiler():
    """Verify ResourceProfiler records memory and CPU metrics."""
    profiler = ResourceProfiler(sample_interval_sec=0.01)
    profiler.start()

    # Do some CPU work
    _ = sum(i * i for i in range(500_000))

    summary = profiler.stop()
    assert summary.ram_baseline_mb > 0
    assert summary.ram_peak_mb >= summary.ram_baseline_mb
    assert summary.cpu_average_percent >= 0.0
    assert summary.cpu_peak_percent >= 0.0


def test_latency_percentiles_calculation():
    """Verify accurate percentile computation."""
    latencies = [100.0, 200.0, 300.0, 400.0, 500.0]
    p = compute_latency_percentiles(latencies)
    assert p.p50 == 300.0
    assert p.min == 100.0
    assert p.max == 500.0
    assert p.mean == 300.0


def test_metrics_computations():
    """Verify biometric and PAD metrics calculations."""
    results = [
        # Genuine match (live)
        ProbeEvaluationResult(
            probe_id="P1",
            true_identity="EMP001",
            is_live_ground_truth=True,
            attack_type=None,
            status="verified",
            liveness_score=85.0,
            liveness_passed=True,
            matched_identity="EMP001",
            similarity=0.88,
            is_match_above_threshold=True,
            rank1_correct=True,
            latency_total_ms=450.0,
        ),
        # Genuine match (live but falsely rejected by similarity)
        ProbeEvaluationResult(
            probe_id="P2",
            true_identity="EMP002",
            is_live_ground_truth=True,
            attack_type=None,
            status="unrecognized",
            liveness_score=80.0,
            liveness_passed=True,
            matched_identity="EMP002",
            similarity=0.30,
            is_match_above_threshold=False,
            rank1_correct=True,
            latency_total_ms=500.0,
        ),
        # Impostor (live, correctly rejected)
        ProbeEvaluationResult(
            probe_id="P3",
            true_identity=None,
            is_live_ground_truth=True,
            attack_type=None,
            status="unrecognized",
            liveness_score=75.0,
            liveness_passed=True,
            matched_identity="EMP001",
            similarity=0.25,
            is_match_above_threshold=False,
            rank1_correct=False,
            latency_total_ms=400.0,
        ),
        # Attack presentation (spoof print, successfully blocked)
        ProbeEvaluationResult(
            probe_id="P4",
            true_identity="EMP001",
            is_live_ground_truth=False,
            attack_type="print",
            status="spoof_rejected",
            liveness_score=35.0,
            liveness_passed=False,
            matched_identity="EMP001",
            similarity=0.85,
            is_match_above_threshold=True,
            rank1_correct=True,
            latency_total_ms=350.0,
        ),
    ]

    rec, live, lat, _ = compute_metrics(results, similarity_threshold=0.40, liveness_threshold=70.0)

    # Genuine: 2 probes, 1 accept, 1 reject -> TAR = 50%, FRR = 50%
    assert rec.total_genuine_probes == 2
    assert rec.tar_percent == 50.0
    assert rec.frr_percent == 50.0

    # Impostor: 1 probe, 0 accepts -> FAR = 0.0%
    assert rec.total_impostor_probes == 1
    assert rec.far_percent == 0.0

    # Liveness: 3 bona fide (P1, P2, P3), all passed -> BPCER = 0.0%
    assert live.total_bona_fide == 3
    assert live.bpcer_percent == 0.0

    # Attacks: 1 attack (P4), 0 passed -> APCER = 0.0%
    assert live.total_attacks == 1
    assert live.apcer_percent == 0.0
    assert live.acer_percent == 0.0


def test_end_to_end_benchmark_run(tmp_path):
    """Run full benchmark on local fixtures and verify all output files and fields."""
    out_dir = tmp_path / "benchmark_test_output"

    exit_code = run_benchmark(
        manifest_path=FIXTURES_MANIFEST,
        similarity_threshold=0.40,
        liveness_threshold=70.0,
        output_dir=out_dir,
        warmup=False,
        verbose=False,
    )

    assert exit_code == 0

    results_json = out_dir / "results.json"
    events_csv = out_dir / "events.csv"
    summary_md = out_dir / "summary.md"

    assert results_json.is_file(), "results.json was not generated"
    assert events_csv.is_file(), "events.csv was not generated"
    assert summary_md.is_file(), "summary.md was not generated"

    # Verify JSON structure
    with open(results_json, encoding="utf-8") as f:
        data = json.load(f)

    assert "recognition" in data
    assert "liveness" in data
    assert "latency" in data
    assert "resources" in data
    assert "pass_fail_summary" in data
    assert "events" in data

    # Verify recognition fields
    rec = data["recognition"]
    assert "tar_percent" in rec
    assert "far_percent" in rec
    assert "rank1_accuracy_percent" in rec

    # Verify liveness fields
    live = data["liveness"]
    assert "apcer_percent" in live
    assert "bpcer_percent" in live
    assert "acer_percent" in live

    # Verify latency fields
    lat = data["latency"]["overall"]
    assert "p50_ms" in lat
    assert "p95_ms" in lat
    assert "p99_ms" in lat
    assert "mean_ms" in lat

    # Verify resource fields
    res = data["resources"]
    assert "cpu_average_percent" in res
    assert "cpu_peak_percent" in res
    assert "ram_peak_mb" in res
    assert "gpu_available" in res
