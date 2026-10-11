# FaceDeep On-Prem Prototype Benchmark Protocol

## Objective

Run a reproducible, auditable benchmark of the FaceDeep on-prem prototype for attendance-style face identification, passive liveness, end-to-end performance, and a controlled AWS Rekognition comparison.

This protocol must be executed without committing customer biometric media, credentials, or sensitive benchmark outputs to git.

## 1. Freeze the test definition

Before running the final benchmark:

1. Resolve or explicitly document unresolved customer questions from `acceptance-criteria.md`.
2. Record the git commit under test.
3. Record the branch name.
4. Record the FaceDeep API version.
5. Record the recognition model/version.
6. Record the liveness implementation/version.
7. Record the configured recognition threshold.
8. Record all liveness thresholds.
9. Record runtime environment variables that affect inference without recording secrets.
10. Record hardware, operating system, container/runtime versions, and whether GPU acceleration is enabled.
11. Freeze the dataset manifest and hash it.
12. Do not change thresholds or preprocessing after the final evaluation starts.

Any configuration change after step 12 invalidates the final benchmark and requires a fresh run identifier.

## 2. Required benchmark artifacts

Create a run directory outside git for sensitive material, for example:

`$FACEDEEP_BENCHMARK_ROOT/<run-id>/`

Recommended contents:

```
<run-id>/
  manifest/
    enrollment.csv
    tuning.csv
    evaluation.csv
    attacks.csv
  results/
    facedeep-recognition.csv
    facedeep-liveness.csv
    facedeep-performance.csv
    aws-recognition.csv
    comparison-summary.json
  logs/
  environment/
    runtime.json
    hardware.json
    versions.txt
```

Only sanitized, non-biometric aggregate summaries may be copied into the repository.

## 3. Manifest schema

Each media sample must have an opaque sample identifier. Do not use names, employee numbers, email addresses, or other direct identifiers in repository-tracked files.

Minimum manifest columns:

| Column | Meaning |
|---|---|
| sample_id | Opaque unique sample ID. |
| identity_id | Opaque identity label shared across that identity's samples. |
| split | `enrollment`, `tuning`, or `evaluation`. |
| presentation | `bona_fide` or `attack`. |
| attack_type | Empty for bona fide; otherwise e.g. `print`, `screen_replay`, `video_replay`. |
| session_id | Capture session identifier. |
| device_id | Opaque camera/device identifier. |
| lighting | Controlled label such as `normal`, `dim`, `bright`. |
| pose | Controlled label such as `frontal`, `left`, `right`. |
| expected_identity | Opaque expected identity or `none` for impostor/open-set trials. |
| file_uri | Secure local path or object reference outside git. |
| sha256 | SHA-256 of the media file. |

Validate that no identical SHA-256 appears across enrollment/tuning/evaluation unless explicitly justified and excluded from scored results.

## 4. Dataset preparation

### 4.1 Enrollment set

- Use only authorized samples.
- Keep enrollment media separate from evaluation media.
- Use the same intended enrollment references for FaceDeep and AWS when the service workflow permits.
- Record the number of enrolled samples per identity.

### 4.2 Tuning set

Use the tuning set only to:

- choose the FaceDeep similarity threshold;
- choose liveness thresholds if this prototype explicitly allows threshold tuning;
- validate harness behavior;
- identify broken samples before the final run.

Never move a failed final-evaluation sample into tuning and rerun while calling the result final.

### 4.3 Final evaluation set

For the engineering minimum:

- >=30 enrolled identities;
- >=300 genuine closed-set queries total;
- >=10,000 impostor comparisons;
- at least two capture sessions or materially different conditions per identity where practical;
- liveness bona-fide samples;
- each agreed attack category represented.

If customer acceptance requires a larger or different dataset, use the customer-approved requirement and record it in the run metadata.

## 5. Environment preparation

1. Checkout the frozen benchmark commit.
2. Start the on-prem dependencies using the documented deployment method.
3. Confirm database/vector store isolation for the benchmark namespace.
4. Confirm no pre-existing benchmark identities remain.
5. Confirm model files are present locally.
6. Start FaceDeep.
7. Record service startup timestamp.
8. Run one explicitly labeled cold request.
9. Run warm-up requests until model initialization is complete.
10. Record the number and duration of warm-up requests.
11. Do not include warm-up calls in warmed latency percentiles.

The current v2 recognition path is `POST /api/v2/face/recognize`; it runs passive liveness before embedding extraction/search.

## 6. FaceDeep enrollment

For each enrollment sample:

1. Call the FaceDeep enrollment endpoint using the opaque `identity_id`.
2. Record request result, processing time, and any enrollment error.
3. Verify the expected number of identities appears in the benchmark namespace.
4. If enrollment fails, fix the dataset/runtime issue before the final benchmark starts or mark the identity excluded with a documented reason.

Do not silently drop identities after seeing final recognition results.

## 7. Recognition threshold selection

Using only tuning data:

1. Generate genuine/mated comparisons.
2. Generate impostor/non-mated comparisons.
3. Sweep candidate similarity thresholds.
4. For each threshold compute TAR, FAR, and FRR.
5. Select the operating threshold that satisfies `FAR <= 0.1%` while maximizing TAR.
6. Record the selected threshold and the tuning-set denominators.
7. Freeze the selected threshold.
8. Restart or reconfigure the service as required.
9. Record the runtime threshold actually loaded by the application.

The final-set result is invalid if the threshold changes after final evaluation begins.

## 8. Final FaceDeep recognition run

For every final bona-fide closed-set query:

1. Submit the exact evaluation image.
2. Record:
   - sample_id;
   - expected_identity;
   - predicted_identity;
   - response status;
   - similarity/confidence;
   - recognition threshold;
   - liveness status;
   - server processing_time_ms;
   - client-observed end-to-end latency_ms;
   - HTTP status;
   - error category if applicable.
3. Mark the result correct only when the returned identity equals expected_identity and the sample passes the defined liveness gate.

For impostor/FAR trials, construct non-mated comparisons from the frozen manifest and record accepted/rejected outcome at the frozen threshold.

Compute:

- top-1 identification accuracy;
- TAR;
- FAR;
- FRR;
- numerator and denominator for every metric;
- 95% confidence intervals where the harness supports them.

## 9. Passive liveness run

Liveness must be scored independently of recognition.

For each bona-fide or attack sample record:

- sample_id;
- presentation type;
- attack_type;
- liveness status;
- liveness score;
- layer/component results when available;
- latency;
- error.

Compute:

`BPCER = bona_fide_rejected / total_bona_fide`

For each attack category:

`APCER(category) = attacks_accepted_as_live / total_attacks_in_category`

Also report an overall APCER, but never omit per-category results.

Pass criteria are defined in `acceptance-criteria.md`. Missing an agreed attack category means liveness acceptance is incomplete.

## 10. Performance benchmark

### 10.1 Primary warmed sequential test

After warm-up:

1. Use representative authorized evaluation images.
2. Execute at least 200 end-to-end recognition requests.
3. Measure on the client from request start through receipt of the final employee/non-match response.
4. Record server processing time separately when returned.
5. Sample CPU and RAM throughout.
6. Sample GPU utilization/memory if applicable.

Report:

- p50;
- p95;
- p99;
- mean;
- min/max;
- successful-request rate;
- timeout/error count;
- CPU summary;
- RAM peak/mean;
- GPU summary if used.

Primary pass threshold: `p95 <= 2.0 s`.

### 10.2 Concurrency/throughput test

Run declared concurrency levels, for example 1, 2, 4, and 8 concurrent clients, or the customer-approved peak-load profile.

For each level report:

- total requests;
- duration;
- requests/second;
- p50/p95/p99;
- error rate;
- CPU/GPU/RAM.

Do not claim a throughput result without naming concurrency and hardware.

### 10.3 Cold-start test

From a stopped service:

1. start the service;
2. time until health is ready;
3. issue the first recognition request;
4. record first-request latency;
5. record when steady warmed behavior begins.

Report cold-start separately from warmed performance.

## 11. AWS Rekognition comparison

Use the same frozen authorized manifest and expected labels.

Before the AWS run, record:

- AWS region;
- Rekognition API workflow used;
- collection/index configuration;
- SDK/API version;
- client host;
- network path;
- request timeout/retry settings;
- cost-relevant request counts.

For every sample that is semantically comparable:

1. use the same evaluation media used for FaceDeep;
2. use the same expected identity label;
3. record AWS returned candidate/identity and similarity/confidence;
4. record full client-observed cloud latency including network;
5. record API errors/retries;
6. do not remove hard samples from one system only.

Compute the same recognition metrics where semantics allow.

If AWS does not provide a directly equivalent passive-liveness function in the selected workflow, mark liveness as `not directly comparable`; do not substitute face-match confidence as a liveness metric.

## 12. Comparison report

Produce one comparison table with explicit denominators:

| Metric | FaceDeep | AWS Rekognition | Notes |
|---|---:|---:|---|
| Top-1 identification accuracy | | | same final queries |
| TAR | | | fixed declared policy |
| FAR | | | same impostor definition where comparable |
| FRR | | | same genuine definition |
| BPCER | | N/A or measured | only if semantically comparable |
| APCER print | | N/A or measured | |
| APCER screen replay | | N/A or measured | |
| p50 latency | | | FaceDeep local vs AWS network-inclusive |
| p95 latency | | | |
| p99 latency | | | |
| error rate | | | |
| tested request count | | | |
| estimated AWS request cost | N/A | | |

Do not create a single weighted "winner score" unless a customer-approved weighting exists.

## 13. Pass/fail evaluation

Evaluate each mandatory gate independently against `acceptance-criteria.md`.

The run outcome must be one of:

- **PASS** — all applicable mandatory gates pass;
- **FAIL** — at least one mandatory gate fails;
- **INCOMPLETE** — dataset, attack coverage, environment metadata, or comparison evidence is insufficient to evaluate a mandatory gate.

An incomplete gate must never be reported as a pass.

## 14. Reproducibility checklist

A second engineer must be able to repeat the run from the documentation and non-secret configuration.

Before publishing the result, verify:

- [ ] git commit recorded;
- [ ] runtime versions recorded;
- [ ] hardware recorded;
- [ ] all threshold values recorded;
- [ ] dataset manifest hash recorded;
- [ ] enrollment/tuning/evaluation split validated;
- [ ] sample counts recorded;
- [ ] warm-up procedure recorded;
- [ ] concurrency recorded;
- [ ] FaceDeep raw result file exists outside git;
- [ ] liveness raw result file exists outside git;
- [ ] AWS raw result file exists outside git when comparison is run;
- [ ] aggregate metrics can be regenerated from raw result files;
- [ ] no biometric media is committed;
- [ ] no API key/credential is committed.

## 15. Suggested run metadata

Record a machine-readable metadata file outside git containing at least:

```json
{
  "run_id": "YYYYMMDD-HHMM-<short-sha>",
  "git_commit": "<sha>",
  "api_version": "v2",
  "recognition_threshold": "<frozen value>",
  "liveness_thresholds": {},
  "dataset_manifest_sha256": "<hash>",
  "identity_count": 0,
  "genuine_query_count": 0,
  "impostor_trial_count": 0,
  "hardware": {},
  "software_versions": {},
  "aws_region": "<if used>",
  "started_at": "<UTC ISO-8601>",
  "completed_at": "<UTC ISO-8601>"
}
```

## 16. Failure handling

When a run fails:

1. preserve the failed run's metadata and aggregate evidence outside git;
2. identify the failing gate;
3. make one traceable change;
4. increment the run ID;
5. rerun tuning only if the change legitimately requires it;
6. rerun the complete final evaluation after any threshold/model/preprocessing change;
7. report both the failure and the subsequent result.

Do not overwrite failed evidence or present only the best run.

## 17. Completion criteria for P01

This protocol is considered ready when another engineer can use it to:

- build the authorized split manifests;
- freeze thresholds/configuration;
- run FaceDeep recognition and liveness;
- collect p50/p95/p99 and resource measurements;
- run the same authorized samples through AWS Rekognition;
- calculate the defined metrics;
- make a deterministic PASS/FAIL/INCOMPLETE decision using `acceptance-criteria.md`.

All customer-specific unknowns are listed in the Customer open questions section of `acceptance-criteria.md`.
