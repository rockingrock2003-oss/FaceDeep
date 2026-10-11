# FaceDeep On-Prem Prototype Acceptance Criteria

## Purpose

This document defines the measurable success criteria for the five-day FaceDeep on-prem prototype. It applies only to the prototype flow and must not be interpreted as a production SLA, certification, or generalized accuracy claim.

The prototype flow is:

1. Tablet/front camera captures a face automatically.
2. The captured image is submitted to the FaceDeep on-prem API.
3. Passive liveness is evaluated.
4. Only a liveness-passed sample proceeds to face recognition.
5. FaceDeep returns an employee identity or a non-match result.
6. The client displays the employee result and records timing/outcome evidence.

The current implementation path is `POST /api/v2/face/recognize`, which performs passive liveness before recognition. Recognition uses the configured FaceDeep similarity threshold; the repository default is currently `FACE_RECOGNITION_THRESHOLD=0.4`. The benchmark must record the exact runtime value used.

## Acceptance principles

- Recognition, liveness, and performance are separate gates.
- A result is not accepted because a single aggregate "accuracy" number is high.
- Enrollment samples and evaluation samples must be disjoint.
- Threshold selection must be completed before the final test split is evaluated.
- FaceDeep and AWS Rekognition must receive the same authorized evaluation samples under the same comparison rules.
- Customer biometric data, credentials, and sensitive benchmark outputs must remain outside git.
- Any target below that depends on a customer decision is provisional until the corresponding customer question is resolved.

## Dataset rules

The benchmark dataset must satisfy all of the following before any pass/fail claim is made:

| Rule | Requirement | Pass/fail |
|---|---|---|
| Authorization | Every person and sample is explicitly authorized for prototype evaluation. | Pass only if authorization is documented outside git. |
| Identity separation | Enrollment, threshold-tuning, and final evaluation sets are disjoint by sample. | Pass only if no evaluation image appears in enrollment/tuning. |
| Final-set isolation | The final evaluation split is not used to tune thresholds, preprocessing, model parameters, or liveness rules. | Pass only if threshold/config freeze occurs first. |
| Identity count | At least 30 enrolled identities for engineering acceptance; customer acceptance requires the customer-approved identity count. | Fail engineering benchmark below 30 identities. |
| Genuine queries | At least 10 final bona-fide query samples per identity where practical, with at least 300 genuine queries total. | Fail engineering benchmark below 300 genuine queries. |
| Impostor trials | At least 10,000 non-mated recognition comparisons for FAR estimation. | Fail FAR acceptance below 10,000 impostor trials. |
| Capture variation | Final bona-fide set must include at least two sessions or materially different capture conditions per identity where practical. | Record as limitation and do not claim representative attendance performance if absent. |
| Attack coverage | Liveness evaluation must include bona-fide samples and all agreed presentation-attack categories. | No overall liveness pass if an agreed attack category is absent. |
| Reproducibility | Each sample is referenced by an opaque sample ID, identity label, split, category, and capture metadata. | Pass only if a second engineer can reconstruct the manifest. |
| Privacy | Raw biometric media and sensitive result files are excluded from git. | Any committed biometric sample is an automatic fail. |

For customer-facing acceptance, the customer-approved dataset definition overrides the engineering minimums above, but it may not weaken split isolation, authorization, or privacy rules.

## Recognition acceptance

### Metrics

**Top-1 identification accuracy**

For bona-fide closed-set queries whose identity exists in the gallery:

`top1_accuracy = correct_top1_identifications / total_closed_set_genuine_queries`

**False acceptance rate (FAR)**

For non-mated/impostor comparisons:

`FAR = false_accepts / total_impostor_trials`

**False rejection rate (FRR)**

For mated/genuine verification trials:

`FRR = false_rejects / total_genuine_trials`

**True acceptance rate (TAR)**

`TAR = 1 - FRR`

All four metrics must report numerator, denominator, percentage, configured threshold, and 95% confidence interval where the benchmark harness supports it.

### Threshold policy

1. Select the FaceDeep recognition threshold using only the tuning/validation split.
2. The tuning objective is to achieve `FAR <= 0.1%` on the tuning impostor trials while maximizing TAR.
3. Freeze the threshold before final evaluation.
4. Do not retune after observing final-set failures.
5. Record both the repository default and the frozen benchmark threshold.

### Pass/fail targets

| Requirement | Dataset rule | Pass threshold |
|---|---|---|
| Closed-set identity recognition | Final bona-fide closed-set queries only; identity enrolled; sample not used for enrollment/tuning. | Top-1 identification accuracy >= 99.0%. |
| False acceptance control | Final impostor trials only; at least 10,000 trials. | FAR <= 0.1%. |
| Genuine acceptance | Final genuine verification trials only. | TAR >= 99.0% (equivalently FRR <= 1.0%). |
| Threshold integrity | Threshold fixed before final evaluation. | Zero post-test threshold changes. |
| Result traceability | Every query records expected identity, predicted identity, similarity, threshold, and outcome. | 100% of benchmark queries traceable. |

The phrase "99% accuracy" must never be used by itself. Any 99% statement must name the metric, dataset split, denominator, threshold, and capture conditions. If the customer-approved dataset cannot support the claim, report the measured value without claiming >=99%.

## Passive liveness acceptance

Liveness is evaluated separately from recognition. Recognition accuracy cannot compensate for a liveness failure.

### Metrics

**APCER — Attack Presentation Classification Error Rate**

`APCER = attack_presentations_incorrectly_classified_as_bona_fide / total_attack_presentations`

APCER must be reported separately for each attack category and as an overall aggregate.

**BPCER — Bona Fide Presentation Classification Error Rate**

`BPCER = bona_fide_presentations_incorrectly_classified_as_attack / total_bona_fide_presentations`

### Required attack categories

The final customer-approved list must be confirmed before acceptance. The engineering protocol must support at least:

- printed-photo presentation;
- phone/tablet screen replay of a face image;
- video replay where available;
- any customer-nominated attack relevant to the attendance kiosk.

### Pass/fail targets

| Requirement | Dataset rule | Pass threshold |
|---|---|---|
| Bona-fide usability | Authorized live captures, final liveness split. | BPCER <= 5.0%. |
| Printed-photo resistance | Final print-attack samples. | APCER <= 5.0%. |
| Screen-replay resistance | Final screen-replay samples. | APCER <= 5.0%. |
| Video-replay resistance | Final video-replay samples when this category is in scope. | APCER <= 5.0%. |
| Category completeness | Every agreed attack category has a reported denominator and APCER. | 100% of agreed categories reported. |
| Separation from recognition | Liveness metrics are reported independently from recognition metrics. | No combined "accuracy" number used as a substitute. |

These thresholds are prototype engineering gates, not an ISO/IEC 30107 certification claim.

## End-to-end performance acceptance

The primary user-perceived timer starts when the kiosk has a captured image ready for submission and ends when the employee/non-match result is available to the kiosk client.

The benchmark must also record server-side processing time where available, but server-side timing alone does not replace end-to-end timing.

### Metrics

- p50 end-to-end latency;
- p95 end-to-end latency;
- p99 end-to-end latency;
- requests/second at the tested concurrency;
- CPU utilization;
- GPU utilization if a GPU is used;
- resident memory/RAM;
- model warm-up duration;
- cold-start latency separately from warmed latency;
- error rate and timeout count.

### Pass/fail targets

| Requirement | Dataset/load rule | Pass threshold |
|---|---|---|
| Primary latency | Warmed runtime; representative prototype images; at least 200 sequential requests. | p95 <= 2.0 seconds. |
| Tail latency | Same run as primary latency. | p99 <= 3.0 seconds. |
| Median latency | Same run as primary latency. | p50 <= 1.5 seconds. |
| Reliability | Same performance run. | Successful response rate >= 99.0%, excluding intentionally invalid samples. |
| Warm-up | From process start until the first fully initialized successful recognition request. | Measured and reported; no hidden warm-up requests. |
| Resource reporting | During the full performance run. | CPU and RAM recorded; GPU recorded when applicable. |
| Throughput | Fixed hardware/configuration and declared concurrency. | Measured and reported; no pass claim without stating concurrency. |

If the final tablet-to-result path introduces additional client capture/network latency, that latency must be included in the final kiosk benchmark rather than inferred from API-only timing.

## FaceDeep vs AWS Rekognition comparison acceptance

The comparison is valid only if both systems are evaluated from the same frozen manifest.

Required controls:

- same authorized identities;
- same enrollment/reference images where the APIs permit equivalent use;
- same final query images;
- same closed-set and impostor trial definitions;
- same inclusion/exclusion rules;
- same expected identity labels;
- same network environment documented for cloud calls;
- FaceDeep on-prem latency and AWS network-inclusive latency both reported explicitly;
- no FaceDeep threshold tuning on AWS results and no cherry-picking samples per system.

The comparison table must include at least:

- top-1 identification accuracy or the closest explicitly defined AWS-equivalent result;
- TAR/FRR at the declared decision policy where comparable;
- FAR where comparable;
- per-category liveness results only if the compared AWS service supports the same passive-liveness scope;
- p50/p95/p99 latency;
- failed/error request count;
- cost notes for AWS requests;
- tested hardware and software versions.

If a metric is not semantically comparable between the two systems, mark it "not directly comparable" rather than forcing a combined score.

## Prototype outcome decision

The prototype is **PASS** only when all applicable mandatory gates pass:

1. authorized and valid benchmark dataset;
2. top-1 recognition >= 99.0% on the approved closed-set final set;
3. FAR <= 0.1%;
4. FRR <= 1.0%;
5. each agreed passive-liveness category meets its APCER target;
6. BPCER <= 5.0%;
7. end-to-end p95 <= 2.0 seconds;
8. benchmark artifacts contain the required traceability and runtime metadata;
9. AWS comparison uses the same frozen manifest;
10. no sensitive biometric data or credentials are committed to git.

A failed mandatory gate must be reported as a failure, not averaged away.

## Known assumptions

- The prototype is an attendance-style, primarily 1:N identification flow.
- The camera is a tablet/front-facing camera and produces still-image submissions for the current API path.
- Passive liveness occurs before recognition.
- The current codebase uses ArcFace/InsightFace embeddings and a vector store for nearest-neighbor search.
- The default recognition threshold is 0.4, but the final benchmark threshold must be selected and frozen by the benchmark protocol.
- The five-day prototype can establish engineering evidence but does not constitute production certification.
- AWS network latency will vary by region/connectivity and must be measured rather than estimated.
- No production customer biometric dataset is assumed to be available until explicitly authorized.

## Customer open questions

The following questions must be resolved for final customer acceptance. Until then, the engineering minimums in this document apply only as prototype gates.

1. How many employees must the customer acceptance dataset contain?
2. How many enrollment images per employee will be available?
3. What tablet/front-camera models and resolutions are in scope?
4. Must the system work offline at the kiosk, or is LAN connectivity to an on-prem server guaranteed?
5. Which lighting, pose, glasses, masks, headwear, and distance conditions are mandatory?
6. Which presentation attacks must be accepted as in-scope: print, phone replay, tablet replay, video replay, masks, or others?
7. Is `FAR <= 0.1%` acceptable for the attendance threat model, or does the customer require a stricter operating point?
8. Is the >=99% recognition target specifically top-1 closed-set identification accuracy, TAR at a fixed FAR, or another contract metric?
9. What maximum BPCER is acceptable for normal employee use?
10. Does the p95 <=2s target include camera auto-capture time, network time, kiosk UI rendering, and database write time?
11. What concurrency/requests-per-second represents peak attendance traffic?
12. What on-prem CPU/GPU/RAM hardware will be used for acceptance?
13. Which AWS region and Rekognition API workflow should be used for the comparison?
14. May benchmark metadata be retained after testing, and what is the required deletion/retention period for biometric media?
15. What constitutes an attendance success result: identity only, identity plus timestamp, or identity plus downstream attendance-system acknowledgement?

## Evidence required at completion

P01 is complete when this document and `benchmark-protocol.md` exist, all metrics above have dataset rules and thresholds, the benchmark can be repeated by another engineer, and no standalone vague "99% accuracy" acceptance criterion remains.
