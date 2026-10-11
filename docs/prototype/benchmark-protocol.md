# FaceDeep On-Premise Prototype: Benchmark & Evaluation Protocol

**Document Version:** 1.0.0  
**Status:** Approved Protocol  
**Target Branch:** `docs/prototype-acceptance`  
**Target System:** FaceDeep On-Premise Edge & Kiosk Prototype vs AWS Rekognition  

---

## 1. Objective & Reproducibility Standard

The objective of this protocol is to define a **strictly reproducible, transparent, and fair benchmarking procedure** for evaluating:
1. **FaceDeep On-Premise Biometric Engine** (InsightFace ArcFace `buffalo_l` + multi-layer passive liveness).
2. **AWS Rekognition Comparison Baseline** (`CompareFaces` and `SearchFacesByImage` APIs).

This document serves as an actionable playbook. Any systems or QA engineer following this protocol must be able to reproduce identical metric outcomes within statistical measurement tolerances.

---

## 2. Dataset Architecture & Privacy Rules

### 2.1 Strict Biometric Data Privacy & Security Governance
In accordance with GDPR, CCPA, and Illinois BIPA compliance:
- **Zero Sensitive Biometrics in Version Control:** Never commit real employee face images, customer evaluation sets, AWS API access keys, or raw biometric embeddings into Git repositories.
- **Git Protection:** Ensure `.gitignore` explicitly ignores:
  ```gitignore
  data/
  datasets/
  benchmark_results/
  *.onnx
  *.lock
  .env
  ```
- **Consent & Synthetic Cohorts:** All benchmarking must use either:
  1. Internal consented employee test sets with signed biometric processing releases, or
  2. Publicly licensed benchmark validation sets (e.g., LFW, CFP-FP, CASIA-SURF for PAD) or synthetically generated identities.

### 2.2 Dataset Directory Structure

Evaluation datasets must be organized in a standardized directory format on the local benchmark runner filesystem:

```
benchmark_data/
├── manifest.json                  # Machine-readable test definitions & ground truth
├── gallery/                       # Enrolled reference images (1 per employee)
│   ├── EMP0001_enroll.jpg
│   ├── EMP0002_enroll.jpg
│   └── ...
├── probes_genuine/                # Bona fide live probe images (same employees)
│   ├── EMP0001_probe_01.jpg       # Normal indoor illumination
│   ├── EMP0001_probe_02.jpg       # Dim lighting (approx 150 lux)
│   ├── EMP0001_probe_03.jpg       # Slight pose (15° yaw)
│   └── ...
├── probes_impostor/               # Bona fide probes of unenrolled identities
│   ├── STRANGER0001.jpg
│   ├── STRANGER0002.jpg
│   └── ...
└── probes_spoof/                  # Presentation Attack Instruments (PAI)
    ├── level1_print/              # Printed photos (matte, gloss, cutouts)
    │   ├── EMP0001_matte_print.jpg
    │   └── EMP0002_gloss_print.jpg
    └── level2_screen/             # Digital screen replays (tablet, OLED smartphone)
        ├── EMP0001_ipad_replay.jpg
        └── EMP0002_oled_phone.jpg
```

### 2.3 Ground Truth Manifest Schema (`manifest.json`)

To prevent ambiguous evaluation rules, the test harness consumes a standardized manifest:

```json
{
  "benchmark_version": "1.0",
  "gallery_size": 500,
  "records": [
    {
      "probe_id": "P_001",
      "image_path": "probes_genuine/EMP0001_probe_01.jpg",
      "expected_identity": "EMP0001",
      "is_bona_fide": true,
      "presentation_attack_type": null,
      "illumination_lux": 450,
      "pose_category": "frontal"
    },
    {
      "probe_id": "P_002",
      "image_path": "probes_spoof/level1_print/EMP0001_matte_print.jpg",
      "expected_identity": "EMP0001",
      "is_bona_fide": false,
      "presentation_attack_type": "level1_matte_print",
      "illumination_lux": 450,
      "pose_category": "frontal"
    }
  ]
}
```

---

## 3. FaceDeep vs AWS Rekognition Fair Comparison Protocol

To avoid biased or deceptive comparisons, FaceDeep and AWS Rekognition must be evaluated under **strict parity conditions**.

```
                           ┌───────────────────────────────┐
                           │   Standard Probe Image Feed   │
                           │     (Exact Same Byte Stream)  │
                           └───────────────┬───────────────┘
                                           │
                   ┌───────────────────────┴───────────────────────┐
                   ▼                                               ▼
     ┌───────────────────────────┐                   ┌───────────────────────────┐
     │    FaceDeep On-Premise    │                   │      AWS Rekognition      │
     │     Local Edge Engine     │                   │       Cloud Service       │
     ├───────────────────────────┤                   ├───────────────────────────┤
     │ • Local LAN / Loopback    │                   │ • TLS / WAN Public Route  │
     │ • ArcFace 512-d (CPU/GPU) │                   │ • AWS Managed Neural Net  │
     │ • Built-in Multi-Layer    │                   │ • Separate Face Liveness  │
     │   Passive PAD             │                   │   (Requires SDK / Video)  │
     └─────────────┬─────────────┘                   └─────────────┬─────────────┘
                   │                                               │
                   ▼                                               ▼
       [Metrics: Similarity τ,                         [Metrics: Similarity %,
        TAR/FAR, Local Latency]                         TAR/FAR, WAN + API Latency]
```

### 3.1 Strict Parity Rules

1. **Input Payload Identity:** The exact same binary image files (identical resolution, compression, byte headers, and crop) must be supplied to both engines.
2. **Gallery Parity:** The same reference enrollment image for each employee must be stored in FaceDeep (ChromaDB collection) and indexed in AWS Rekognition (`IndexFaces` into a test `CollectionId`).
3. **Measurement Segmentation (Algorithmic vs Network Overhead):**
   - For **FaceDeep On-Premise**:
     - $T_{\text{alg}}$: Execution time inside the local process (pre-processing + liveness + ArcFace + vector lookup).
     - $T_{\text{net}}$: LAN transfer time between kiosk and local server ($\le 20\text{ ms}$).
     - $T_{\text{total\_facedeep}} = T_{\text{alg}} + T_{\text{net}}$.
   - For **AWS Rekognition**:
     - $T_{\text{aws\_api}}$: Total round-trip time from `boto3` client dispatch to response receipt (includes WAN internet latency, TLS negotiation, cloud queue, and Rekognition execution).
     - Both numbers ($T_{\text{total}}$ and network breakdown) must be logged transparently.
4. **Metric Translation & Threshold Alignment:**
   - FaceDeep uses **Cosine Similarity** $S_c \in [-1.0, 1.0]$ with default operating threshold $\tau = 0.40$ (and high-security $\tau = 0.50$).
   - AWS Rekognition outputs a **Similarity Percentage** $S_{\text{aws}} \in [0.0, 100.0\%]$ with default threshold $80\%$ or $90\%$.
   - The benchmark harness computes the full ROC/DET curve across varying thresholds for both systems, plotting $\text{TAR}$ against $\text{FAR}$ to compare true algorithmic discriminant capability rather than arbitrary nominal percentages.

### 3.2 Evaluation Comparison Matrix

| Evaluation Dimension | FaceDeep On-Premise Prototype | AWS Rekognition Cloud API | Parity / Fairness Constraint |
|---|---|---|---|
| **API Endpoint** | `POST /api/v2/face/recognize` | `SearchFacesByImage` / `CompareFaces` | Identical image bytes sent |
| **Liveness Inspection** | Built-in 3-layer passive PAD | AWS Face Liveness (requires 3D interactive video stream) | FaceDeep passive single-frame PAD reported separately |
| **Data Residency** | 100% on-premise local appliance; zero outbound WAN traffic | Images streamed to AWS public cloud data centers | Highlight data residency compliance (GDPR/BIPA) |
| **Operational Cost** | Flat predictable infrastructure cost | $\$0.0010$ per `SearchFacesByImage` call + data transfer | Cost tracked per 1,000 requests |
| **Internet Dependency** | Zero. Fully functional in air-gapped offline environments | Complete failure during internet outage or WAN jitter | Simulate offline failover |

---

## 4. Benchmark Harness Implementation Architecture

The reproducible benchmark runner is executed via a standardized Python script with configurable arguments.

### 4.1 CLI Execution Syntax

```bash
# 1. Ensure environment dependencies
python3 -m pip install -r requirements.txt
python3 -m pip install boto3 psutil tabulate

# 2. Run FaceDeep local benchmark on evaluation dataset
python3 scripts/benchmark_harness.py \
    --mode facedeep \
    --manifest datasets/benchmark/manifest.json \
    --gallery-dir datasets/benchmark/gallery \
    --probes-dir datasets/benchmark/probes \
    --threshold 0.40 \
    --output-dir benchmark_results/facedeep_run

# 3. Run AWS comparison adapter (using same manifest and samples)
python3 scripts/benchmark_harness.py \
    --mode aws-rekognition \
    --manifest datasets/benchmark/manifest.json \
    --collection-id facedeep-benchmark-eval \
    --threshold 80.0 \
    --output-dir benchmark_results/aws_run

# 4. Generate comparative evaluation report
python3 scripts/benchmark_harness.py \
    --mode compare \
    --facedeep-results benchmark_results/facedeep_run/report.json \
    --aws-results benchmark_results/aws_run/report.json \
    --output-dir benchmark_results/comparison
```

### 4.2 Automated Measurements Collected

The harness must automatically measure and record:

1. **High-Precision Timing:**
   - Nanosecond clock resolution via `time.perf_counter_ns()`.
   - Per-sample latencies: Pre-processing time, Liveness inference time, Embedding extraction time, Vector database match time, Total round-trip time.
   - Aggregate distribution statistics: $p50$, $p90$, $p95$, $p99$, mean, min, max, standard deviation.

2. **Hardware Profiling:**
   - CPU utilization percentage sampled at $100\text{ ms}$ intervals during continuous test streams (`psutil.cpu_percent()`).
   - Memory RSS footprint before test, peak during test, and delta post-test (`psutil.Process().memory_info().rss`).

3. **Biometric & Liveness Classification Counters:**
   - True Positives ($TP$), False Positives ($FP$), True Negatives ($TN$), False Negatives ($FN$).
   - $\text{TAR} = \frac{TP}{TP + FN}$, $\text{FAR} = \frac{FP}{FP + TN}$, $\text{FRR} = \frac{FN}{TP + FN}$.
   - Rank-1 closed-set accuracy percentage.
   - Presentation Attack Detection: $\text{APCER}_{\text{print}}$, $\text{APCER}_{\text{screen}}$, $\text{BPCER}$.

---

## 5. Standardized Output Schema (`report.json`)

The benchmark harness outputs a fully structured JSON report to eliminate subjective interpretation:

```json
{
  "system": "FaceDeep On-Premise Prototype",
  "engine_version": "2.0.0",
  "timestamp_utc": "2026-10-11T12:00:00Z",
  "hardware": {
    "cpu_model": "x86_64 8-core",
    "ram_total_gb": 16.0,
    "execution_provider": "CPUExecutionProvider"
  },
  "parameters": {
    "similarity_threshold": 0.40,
    "liveness_min_score": 70.0,
    "gallery_size": 500
  },
  "dataset_summary": {
    "total_probes": 1000,
    "genuine_live_probes": 500,
    "impostor_live_probes": 300,
    "spoof_attack_probes": 200
  },
  "recognition_metrics": {
    "tar_percentage": 99.2,
    "far_percentage": 0.08,
    "frr_percentage": 0.8,
    "rank1_accuracy_percentage": 99.4,
    "roc_points": [
      {"threshold": 0.35, "tar": 99.6, "far": 0.35},
      {"threshold": 0.40, "tar": 99.2, "far": 0.08},
      {"threshold": 0.45, "tar": 98.4, "far": 0.02},
      {"threshold": 0.50, "tar": 97.6, "far": 0.005}
    ]
  },
  "liveness_metrics": {
    "apcer_level1_print": 0.0,
    "apcer_level2_screen": 1.0,
    "overall_apcer": 0.5,
    "bpcer": 1.2,
    "acer": 0.85
  },
  "performance_metrics": {
    "latency_ms": {
      "p50": 580.4,
      "p90": 890.2,
      "p95": 1020.1,
      "p99": 1410.5,
      "mean": 612.3
    },
    "subsystem_latency_mean_ms": {
      "image_decode_and_crop": 42.1,
      "liveness_layer1_minifasnet": 165.3,
      "liveness_layer2_depth": 140.2,
      "embedding_extraction_arcface": 235.8,
      "chromadb_vector_search": 18.5
    },
    "resource_usage": {
      "peak_cpu_percent": 58.2,
      "average_cpu_percent": 41.5,
      "peak_memory_rss_mb": 2180.5
    }
  },
  "comparison_vs_aws": {
    "latency_p95_delta_ms": -450.2,
    "cost_per_100k_verifications_usd": {
      "facedeep_hardware_amortized": 12.50,
      "aws_rekognition_api_charge": 100.00
    },
    "air_gap_compliant": true
  }
}
```

---

## 6. Engineer Reproduction & Audit Verification Checklist

An engineer must complete the following audit checklist before signing off on prototype milestone completion:

| Step # | Verification Item | Expected Output / Criteria | Engineer Sign-off |
|---|---|---|---|
| **STEP-1** | Model integrity check | `models/MiniFASNetV1SE.onnx` and `models/MiniFASNetV2.onnx` present and checksum verified | [ ] PASS |
| **STEP-2** | Cold-start warm-up verification | Request #1 latency $\le 2000\text{ ms}$; no uninitialized provider hang | [ ] PASS |
| **STEP-3** | Metric decoupling check | Spoof probe rejected at PAD layer; zero false employee matches granted to presentation attacks | [ ] PASS |
| **STEP-4** | End-to-end latency constraint | Benchmark run of $\ge 200$ samples satisfies $p95 \le 2000\text{ ms}$ | [ ] PASS |
| **STEP-5** | Biometric threshold check | Rank-1 accuracy $\ge 99.0\%$ on closed-set $N=500$ gallery at $\tau = 0.40$ | [ ] PASS |
| **STEP-6** | Impostor rejection check | Impostor probes cross-matched against gallery produce $\text{FAR} \le 0.1\%$ | [ ] PASS |
| **STEP-7** | Air-gap & privacy verification | Zero outbound network calls initiated to external cloud APIs during FaceDeep local mode | [ ] PASS |
| **STEP-8** | Report artifact generation | Output files `report.json`, `events.csv`, and `summary.md` generated without warnings | [ ] PASS |
