# FaceDeep Reproducible Benchmark Harness

A standardized, reproducible benchmark runner for the **FaceDeep On-Premise Prototype**. Evaluates facial recognition accuracy, passive presentation attack detection (PAD), end-to-end latency percentiles ($p50/p95/p99$), and edge hardware resource consumption (CPU and RAM/VRAM).

---

## 1. Quick Start (One-Command Execution)

A fresh clone can run the benchmark out of the box using the included fixture dataset with a single command:

```bash
./tools/benchmark/run.sh
```

Or directly via Python module:

```bash
python3 -m tools.benchmark.runner
```

This single command:
1. Loads the fixture manifest (`tools/benchmark/fixtures/manifest.json`).
2. Warms up the inference graphs (eliminating cold-start latency).
3. Enrolls the gallery identities into an isolated benchmark vector collection.
4. Executes and times every probe presentation (genuine, impostor, and spoof attacks).
5. Monitors background CPU and RAM/VRAM usage via continuous sampling.
6. Cleans up the temporary vector collection.
7. Generates machine-readable results (`results.json`, `events.csv`) and a formatted summary (`summary.md`).
8. Prints a formatted metrics scorecard to the terminal.

---

## 2. CLI Options & Parameters

```bash
python3 -m tools.benchmark.runner [OPTIONS]

Options:
  --manifest PATH            Path to dataset manifest (.json or .csv).
                             (default: tools/benchmark/fixtures/manifest.json)
  --threshold FLOAT          Cosine similarity threshold for recognition match.
                             (default: 0.40)
  --liveness-threshold FLOAT Minimum score (0-100) to classify as live.
                             (default: 70.0)
  --output-dir PATH          Directory to write machine-readable reports.
                             (default: tools/benchmark/results)
  --no-warmup                Skip model warm-up phase prior to timing.
  --quiet                    Suppress per-sample live execution logs.
  -h, --help                 Show help message and exit.
```

### Example: Running Custom Customer Evaluation Sets

```bash
python3 -m tools.benchmark.runner \
    --manifest /path/to/customer_eval_manifest.json \
    --threshold 0.45 \
    --liveness-threshold 70.0 \
    --output-dir benchmark_results/customer_run
```

---

## 3. Dataset Manifest Specification

Manifests can be formatted in either **JSON** or **CSV**.

### JSON Format (`manifest.json`)

```json
{
  "name": "FaceDeep-Local-Fixture-v1",
  "description": "Standardized evaluation set",
  "gallery": [
    {
      "person_id": "EMP001",
      "image_path": "dataset/EMP001_gallery.jpg",
      "metadata": {"department": "Engineering"}
    }
  ],
  "probes": [
    {
      "probe_id": "PROBE_EMP001_LIVE",
      "image_path": "dataset/EMP001_probe_live.jpg",
      "expected_identity": "EMP001",
      "is_live": true,
      "attack_type": null
    },
    {
      "probe_id": "PROBE_IMPOSTOR_01",
      "image_path": "dataset/IMPOSTOR_probe_live.jpg",
      "expected_identity": null,
      "is_live": true,
      "attack_type": null
    },
    {
      "probe_id": "PROBE_EMP001_SPOOF",
      "image_path": "dataset/EMP001_probe_spoof_print.jpg",
      "expected_identity": "EMP001",
      "is_live": false,
      "attack_type": "level1_print"
    }
  ]
}
```

*Note: Relative paths in `image_path` are automatically resolved relative to the directory containing the manifest file.*

### Manifest Rules
1. **Gallery (`gallery`):** Every entry must have `person_id` (string) and `image_path` (string).
2. **Probes (`probes`):**
   * `expected_identity`: The enrolled `person_id` if the probe is genuine. Set to `null` (or omit) for unenrolled impostor probes.
   * `is_live`: `true` for bona fide live presentations, `false` for presentation attacks.
   * `attack_type`: Optional category string (e.g., `"level1_print"`, `"level2_screen"`, `"3d_mask"`).
3. **Invalid/Missing Samples:** If a file path is missing or cannot be opened, the harness raises a descriptive `SampleNotFoundError` during validation or flags the probe as `error` with the exact diagnostic message.

---

## 4. Output Artifacts

All benchmark outputs are written to `--output-dir` (default: `tools/benchmark/results/`):

| File | Format | Purpose |
|---|---|---|
| `results.json` | JSON | Machine-readable metrics, latency percentiles, resource stats, and event log. |
| `events.csv` | CSV | Tabular event record for each probe (similarity, liveness score, decision, latency). |
| `summary.md` | Markdown | Executive report formatted for GitHub / documentation portals. |

> **Privacy Rule:** The `tools/benchmark/results/` and `benchmark_results/` directories are strictly ignored by `.gitignore` to prevent any test outputs or biometric metadata from ever being committed to source control.

---

## 5. Metrics Reported

### Biometric Recognition
* **TAR (True Accept Rate):** Proportion of genuine employee presentations correctly matched ($\ge \tau$).
* **FAR (False Accept Rate):** Proportion of impostor presentations incorrectly matched.
* **FRR (False Reject Rate):** Proportion of genuine employee presentations rejected ($1 - \text{TAR}$).
* **Rank-1 Closed-Set Accuracy:** Percentage where the top-1 gallery candidate matches the expected identity.

### Presentation Attack Detection (ISO/IEC 30107-3)
* **APCER (Attack Presentation Classification Error Rate):** Percentage of spoof attacks falsely accepted as live.
* **BPCER (Bona Fide Presentation Classification Error Rate):** Percentage of live employee presentations falsely flagged as spoof.
* **ACER (Average Classification Error Rate):** $(\text{APCER} + \text{BPCER}) / 2$.

### Performance & Latency
* **Percentiles:** $p50$, $p90$, $p95$, $p99$, mean, min, max, standard deviation.
* **Subsystem Breakdown:** Input I/O, Liveness inference, Embedding extraction, Vector gallery search.

### Resource Utilization
* **CPU:** Average and Peak CPU percentage during the benchmark run.
* **RAM (RSS):** Baseline memory, Peak memory (MB), and Delta.
* **GPU / VRAM:** Device model and allocated/peak VRAM (or `N/A (CPU Execution Provider)` when running on CPU).

---

## 6. Running Automated Tests

To run the unit and integration test suite:

```bash
pytest tests/test_benchmark_harness.py -v
```
