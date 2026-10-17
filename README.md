# FaceGate

A self-hosted face recognition service that speaks Amazon Rekognition's API.
An attendance app built on Rekognition changes only its **endpoint URL** and
**access key**. It keeps the same SDK calls, the same request and response
JSON, and the same error types.

```python
rekognition = boto3.client(
    "rekognition",
    endpoint_url="https://facegate.internal:8000",   # <- the only code change
    aws_access_key_id=..., aws_secret_access_key=...,
    region_name="us-east-1",
)
rekognition.search_faces_by_image(CollectionId="employees", Image={"Bytes": selfie}, FaceMatchThreshold=95)
```

## What is implemented

| Rekognition operation | Status | Notes |
|---|---|---|
| CreateCollection / DeleteCollection / ListCollections / DescribeCollection | ✅ | pagination, ARNs, `ResourceAlreadyExists` / `ResourceNotFound` |
| IndexFaces | ✅ | `ExternalImageId`, `MaxFaces`, `QualityFilter` (NONE/AUTO/LOW/MEDIUM/HIGH), `UnindexedFaces` reasons |
| SearchFacesByImage | ✅ | largest face, `FaceMatchThreshold`, `MaxFaces`, `QualityFilter`, "no faces" error identical |
| SearchFaces | ✅ | by `FaceId` |
| ListFaces / DeleteFaces | ✅ | pagination, `UserId` / `FaceIds` filters, association rule |
| DetectFaces | ✅ (DEFAULT attributes) | `BoundingBox`, `Landmarks`, `Pose`, `Quality`, `Confidence`; age/emotion etc. not implemented |
| CompareFaces | ✅ | `SimilarityThreshold`, `UnmatchedFaces` |
| CreateUser / DeleteUser / ListUsers / AssociateFaces / DisassociateFaces / SearchUsers / SearchUsersByImage | ✅ | `UserMatchThreshold`, `LOW_MATCH_CONFIDENCE`, etc. |
| CreateFaceLivenessSession / GetFaceLivenessSessionResults | ✅ backend API | the device part uses FaceGate's HTTPS endpoints instead of the Amplify streaming component |
| `Image.S3Object` | ✅ | when the server has S3 (or MinIO) credentials |
| SigV4 authentication | ✅ | verified exactly as AWS does it, with a 5-minute clock skew |

`tests/test_rekognition_compat.py` runs the unmodified **boto3** client
against a live server, covering all of the above.

## Beyond Rekognition

* **Passive liveness on every search.** Each `SearchFacesByImage` probe is
  checked for photo, screen and mask spoofs (MiniFASNet ensemble, about 10 ms).
  In `enforce` mode a spoof gets no `FaceMatches`, so the attendance app
  rejects it without any client change.
* **Twins and look-alikes.** Enrolment flags pairs of *different* people
  whose faces are very close. At check-in, if the best match and the best
  different person are too close to call, the match is withheld and the
  response carries `x-facegate-decision: ambiguous`. Rekognition leaves that
  choice to the app.
* **Similarity calibration.** Similarity values are calibrated against
  measured false-accept rates (80 → FAR 1e-3, 90 → 1e-4, 95 → 1e-5,
  99 → 1e-6, from 87.3M LFW impostor pairs). On LFW, the median genuine pair
  scores 99.2. Recommended threshold: 95, as AWS recommends for identity
  verification.
* **Encrypted biometrics.** Face templates and stored face crops are encrypted
  with AES-256-GCM. A wrong key stops the service at startup; records are never
  silently dropped.
* **Model upgrades without re-enrolment.** Aligned face crops are kept
  (encrypted), so `POST /admin/reindex` re-embeds everyone with a new model.
* **Audit log and metrics.** Every call is logged with its latency and decision.
  Prometheus metrics are at `/metrics`.

Extra signals travel in `x-facegate-*` response headers, which AWS SDKs
ignore:

| header | meaning |
|---|---|
| `x-facegate-liveness` | `score=0.97;live=true;mode=enforce` |
| `x-facegate-decision` | `match` / `no_match` / `spoof` / `ambiguous;margin=…` |
| `x-facegate-lookalike` | on IndexFaces: the already-enrolled identity this face resembles |
| `x-facegate-server-ms` | server-side processing time |

## Quick start (Windows / macOS / Linux)

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # Linux/macOS: .venv/bin/pip
python scripts/download_models.py
python scripts/run_demo.py
```

* Kiosk: `https://localhost:8443`, or `https://<laptop-ip>:8443` on an iPad or
  iPhone on the same Wi-Fi. Accept the self-signed certificate once; Safari
  needs HTTPS to open the camera.
* `/enroll` registers employees (camera or photo upload). `/dashboard` shows the
  attendance log.

The demo attendance backend (`demo/attendance_backend.py`) uses **only
boto3**. Unset `REKOGNITION_ENDPOINT` and the same code runs against real
Amazon Rekognition, which you can use for a side-by-side comparison.

## Pilot testing (liveness and recognition)

```bash
python scripts/run_demo.py --debug-probes --password <shared-password>
python scripts/make_pilot_guide.py          # participant guide PDF with the current link
python -m eval.pilot_report --since "2026-10-20 09:00"
```

Open the kiosk with `?pilot=1`: each attempt is started with **Start attempt**
after choosing a label (genuine, stranger, or an attack type) and a participant
ID, and `eval/pilot_report.py` turns the log into attack-acceptance (APCER) and
genuine-rejection (BPCER) rates with 95% bounds. The test plan is in
`docs/PILOT_TEST_PLAN.md`. `--debug-probes` saves every captured frame to
`data/demo/debug-probes/` (biometric data: delete it after the pilot).

To let remote testers in, expose the kiosk with a Cloudflare quick tunnel
(`cloudflared tunnel --url https://localhost:8443 --no-tls-verify`) and always
set `--password` first.

## Production

```bash
cp .env.example .env      # set FACEGATE_CREDENTIALS, FACEGATE_DATA_KEY, FACEGATE_ADMIN_TOKEN
docker compose up -d --build
```

The service needs CPU only. On a laptop CPU it answers a check-in in 49 ms
(p95) and sustains about 46 check-ins per second with 4 kiosks at once.

### Sizing (measured in Docker, 1,000 enrolled faces)

| | value |
|---|---|
| RAM | ~200 MB (1 GB limit is ample) |
| CPU per check-in | ~0.05 s Fast, ~0.6 s Secure (7-frame colour-flash session) |
| 1 vCPU container | ~20 Fast check-ins/s; single-kiosk p95 75 ms |
| Recommended VM | 2 vCPU / 2 GB: up to ~2,000 employees arriving in the same 15 minutes (Secure mode); 4 vCPU / 4 GB up to ~4,000 |

Raw numbers: `reports/latency_docker_1cpu.json`, `reports/latency_docker_2cpu.json`.

## Measured results (LFW, laptop CPU)

| metric | value |
|---|---|
| LFW verification accuracy (6,000 pairs, 10-fold) | 99.38% |
| Attendance simulation, 610 employees, 3 enrolment photos, threshold 95 | 99.19% of decisions correct, 0.041% wrong person, 0.49% strangers accepted |
| Same, 1 enrolment photo, 1,680 employees | 95.6% of decisions correct |
| `SearchFacesByImage` round trip via boto3, 1,000 faces enrolled | p50 38.5 ms, p95 49 ms (1 kiosk); p95 101 ms (4 concurrent) |

Raw numbers are in `reports/`.

## Evaluation

```bash
python -m eval.extract_embeddings --root data/lfw/lfw --out data/eval/lfw_sface.npz
python -m eval.lfw_benchmark --emb data/eval/lfw_sface.npz --pairs data/lfw/pairs.txt \
       --calibration-out models/calibration_sface.json
python -m eval.latency_benchmark --key ... --secret ...
pytest
```

## Licences of the bundled models

| model | use | licence |
|---|---|---|
| YuNet (OpenCV Zoo) | detection | MIT |
| SFace (OpenCV Zoo) | recognition | Apache-2.0 |
| MiniFASNetV2 / V1SE (Silent-Face-Anti-Spoofing) | passive liveness | Apache-2.0 |
| MediaPipe BlazeFace (kiosk, in-browser) | on-device detection | Apache-2.0 |

All of these allow commercial use. The InsightFace `buffalo_l` models used
by the earlier FaceDeep prototype do **not** (non-commercial research only).
