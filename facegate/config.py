"""Runtime configuration.

Every setting can be overridden with an environment variable of the same name
prefixed with ``FACEGATE_`` (e.g. ``FACEGATE_DATA_DIR=/var/lib/facegate``) or a
``.env`` file in the working directory.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FACEGATE_", env_file=".env", extra="ignore")

    # --- service ---------------------------------------------------------
    environment: Literal["development", "production", "test"] = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    data_dir: Path = PROJECT_ROOT / "data" / "runtime"
    models_dir: Path = PROJECT_ROOT / "models"

    # Values echoed back in ARNs so responses look like the AWS originals.
    aws_region: str = "us-east-1"
    aws_account_id: str = "000000000000"
    # Reported as FaceModelVersion. Rekognition currently reports "7.0"; we keep
    # the real engine identity in the x-facegate-model response header.
    reported_face_model_version: str = "7.0"

    # --- authentication --------------------------------------------------
    # "sigv4": verify AWS Signature V4 exactly like AWS does (production).
    # "none":  accept any request (local development only).
    auth_mode: Literal["sigv4", "none"] = "sigv4"
    # Comma separated "ACCESS_KEY_ID:SECRET_ACCESS_KEY" pairs.
    credentials: str = ""
    # Max allowed clock skew for signed requests, seconds (AWS uses 5 minutes).
    max_clock_skew_seconds: int = 300
    # Bearer token for /admin endpoints. Empty disables the admin API.
    admin_token: str = ""

    # --- encryption at rest ----------------------------------------------
    # 32 byte key, base64 encoded. Encrypts face templates and stored crops.
    # In development a key file is generated under data_dir if this is empty.
    data_key: str = ""
    # Keep the aligned 112x112 face crop (encrypted) so the whole collection
    # can be re-embedded when the recognition model is upgraded. Rekognition
    # cannot do this, which is why migrating away from it needs re-enrolment.
    store_face_crops: bool = True

    # --- engine ------------------------------------------------------------
    detector_model: str = "face_detection_yunet_2023mar.onnx"
    recognizer_model: str = "face_recognition_sface_2021dec.onnx"
    # "sface" (OpenCV Zoo, Apache-2.0) or "arcface" (any 112x112 ArcFace-style ONNX).
    recognizer_kind: Literal["sface", "arcface"] = "sface"
    calibration_file: str = "calibration_sface.json"
    detect_max_side: int = 640
    # Coarse first pass for single-face operations (search / compare source).
    fast_detect_side: int = 320
    # Average the template of the image and its mirror image (+1 inference).
    # On for enrolment (once per employee, best template quality); off for
    # check-in probes, where it would double the dominant cost for ~0.2 points
    # of accuracy on LFW.
    flip_augment: bool = True
    flip_augment_probe: bool = False
    detect_score_threshold: float = 0.6
    min_face_px: int = 32
    onnx_threads: int = 2

    # --- passive liveness on SearchFacesByImage --------------------------
    # off:     do nothing
    # report:  score every probe, add x-facegate-liveness header, never block
    # enforce: a probe judged as a spoof returns no FaceMatches (the attendance
    #          app then rejects the check-in without any client change)
    passive_liveness_on_search: Literal["off", "report", "enforce"] = "enforce"
    passive_liveness_on_index: Literal["off", "report", "enforce"] = "report"
    passive_liveness_threshold: float = 0.50

    # Diagnostics only: save every probe image with its scores to this folder
    # (e.g. to tune the liveness threshold in a pilot). Off by default - these
    # are biometric images; delete the folder when done.
    debug_probe_dir: Path | None = None

    # --- liveness sessions (CreateFaceLivenessSession flow) ------------
    liveness_session_ttl_seconds: int = 180
    # white, colour, colour, white, colour, colour, white
    liveness_frames_required: int = 7
    liveness_pass_confidence: float = 70.0
    # Finished and expired sessions (with their encrypted reference images)
    # are deleted this long after they expire.
    liveness_session_retention_seconds: int = 3600

    # --- REST liveness API (/v1/liveness) --------------------------------
    # Comma separated API keys accepted in the x-api-key header. Empty
    # disables the /v1 API.
    api_keys: str = ""
    # Public address used to build captureUrl / resultUrl (e.g.
    # https://liveness.example.com). Empty: taken from the request.
    public_base_url: str = ""

    # --- retention ---------------------------------------------------------
    # Audit log rows older than this are deleted. 0 keeps them forever.
    audit_retention_days: int = 90

    # --- identical twins / look-alikes -------------------------------------
    # If the best match and the best match of a *different* identity are
    # closer than this (raw cosine), the decision is ambiguous.
    ambiguity_margin: float = 0.08
    # Larger margin required when the matched identity has a known look-alike.
    lookalike_margin: float = 0.15
    # Raw cosine above which two different identities are flagged as look-alikes
    # at enrolment time (likely twins / siblings / duplicate enrolment).
    lookalike_threshold: float = 0.55
    # reject: return no matches for ambiguous probes (safe default for attendance)
    # report: return matches unchanged, add x-facegate-decision header
    ambiguity_policy: Literal["reject", "report"] = "reject"

    # --- limits mirrored from Rekognition ----------------------------------
    max_image_bytes: int = 5 * 1024 * 1024
    min_image_side: int = 80

    @property
    def credential_map(self) -> dict[str, str]:
        pairs: dict[str, str] = {}
        for item in self.credentials.split(","):
            item = item.strip()
            if not item:
                continue
            key_id, _, secret = item.partition(":")
            if key_id and secret:
                pairs[key_id.strip()] = secret.strip()
        return pairs

    @property
    def api_key_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    def model_path(self, name: str) -> Path:
        return self.models_dir / name


@lru_cache
def get_settings() -> Settings:
    return Settings()
