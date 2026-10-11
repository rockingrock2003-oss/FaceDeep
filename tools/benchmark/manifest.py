from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ManifestError(Exception):
    """Base exception for manifest parsing and validation errors."""


class ManifestValidationError(ManifestError):
    """Raised when manifest structure or field types are invalid."""


class SampleNotFoundError(ManifestError):
    """Raised when an image/video file referenced in the manifest does not exist."""


@dataclass
class GalleryRecord:
    person_id: str
    image_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "person_id": self.person_id,
            "image_path": str(self.image_path),
            "metadata": self.metadata,
        }


@dataclass
class ProbeRecord:
    probe_id: str
    image_path: Path
    expected_identity: str | None  # None indicates an unenrolled impostor probe
    is_live: bool = True
    attack_type: str | None = None  # e.g., 'print', 'screen', '3d_mask', or None if live
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "image_path": str(self.image_path),
            "expected_identity": self.expected_identity,
            "is_live": self.is_live,
            "attack_type": self.attack_type,
            "metadata": self.metadata,
        }


@dataclass
class BenchmarkManifest:
    name: str
    description: str
    gallery: list[GalleryRecord]
    probes: list[ProbeRecord]
    manifest_path: Path | None = None

    @property
    def total_gallery(self) -> int:
        return len(self.gallery)

    @property
    def total_probes(self) -> int:
        return len(self.probes)

    @property
    def genuine_probes(self) -> list[ProbeRecord]:
        return [p for p in self.probes if p.is_live and p.expected_identity is not None]

    @property
    def impostor_probes(self) -> list[ProbeRecord]:
        return [p for p in self.probes if p.is_live and p.expected_identity is None]

    @property
    def spoof_probes(self) -> list[ProbeRecord]:
        return [p for p in self.probes if not p.is_live]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "total_gallery": self.total_gallery,
            "total_probes": self.total_probes,
            "gallery": [g.to_dict() for g in self.gallery],
            "probes": [p.to_dict() for p in self.probes],
        }


def _resolve_file_path(path_str: str, base_dir: Path) -> Path:
    raw_path = Path(path_str)
    if raw_path.is_absolute():
        return raw_path
    
    # Check relative to manifest directory
    candidate = (base_dir / raw_path).resolve()
    if candidate.exists():
        return candidate
        
    # Check relative to current working directory
    cwd_candidate = Path(path_str).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
        
    return candidate


def load_manifest(
    file_path: str | Path,
    validate_files: bool = True,
) -> BenchmarkManifest:
    """Load and validate a dataset manifest from JSON or CSV.
    
    Args:
        file_path: Path to manifest file (.json or .csv).
        validate_files: If True, validates that all image paths exist on disk.
        
    Returns:
        Validated BenchmarkManifest instance.
        
    Raises:
        FileNotFoundError: If manifest file does not exist.
        ManifestValidationError: If required fields are missing or schema is invalid.
        SampleNotFoundError: If an image referenced in manifest cannot be found.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    base_dir = path.parent

    if path.suffix.lower() == ".json":
        return _load_json_manifest(path, base_dir, validate_files)
    elif path.suffix.lower() == ".csv":
        return _load_csv_manifest(path, base_dir, validate_files)
    else:
        raise ManifestValidationError(
            f"Unsupported manifest format '{path.suffix}'. Expected .json or .csv."
        )


def _load_json_manifest(
    path: Path, base_dir: Path, validate_files: bool
) -> BenchmarkManifest:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ManifestValidationError(f"Invalid JSON syntax in manifest {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestValidationError("Manifest JSON root must be an object/dict")

    name = data.get("name", path.stem)
    description = data.get("description", "")

    # Parse gallery
    gallery_raw = data.get("gallery", [])
    if not isinstance(gallery_raw, list):
        raise ManifestValidationError("Field 'gallery' must be a list of records")

    gallery: list[GalleryRecord] = []
    for idx, item in enumerate(gallery_raw):
        if not isinstance(item, dict):
            raise ManifestValidationError(f"Gallery entry #{idx} must be a dictionary")
        if "person_id" not in item or not str(item["person_id"]).strip():
            raise ManifestValidationError(f"Gallery entry #{idx} is missing required 'person_id'")
        if "image_path" not in item or not str(item["image_path"]).strip():
            raise ManifestValidationError(f"Gallery entry #{idx} is missing required 'image_path'")

        img_path = _resolve_file_path(str(item["image_path"]), base_dir)
        if validate_files and not img_path.is_file():
            raise SampleNotFoundError(
                f"Gallery image for person '{item['person_id']}' not found at: {img_path}"
            )

        gallery.append(
            GalleryRecord(
                person_id=str(item["person_id"]).strip(),
                image_path=img_path,
                metadata=item.get("metadata", {}),
            )
        )

    # Parse probes
    probes_raw = data.get("probes", [])
    if not isinstance(probes_raw, list):
        raise ManifestValidationError("Field 'probes' must be a list of records")

    probes: list[ProbeRecord] = []
    for idx, item in enumerate(probes_raw):
        if not isinstance(item, dict):
            raise ManifestValidationError(f"Probe entry #{idx} must be a dictionary")
        if "probe_id" not in item or not str(item["probe_id"]).strip():
            raise ManifestValidationError(f"Probe entry #{idx} is missing required 'probe_id'")
        if "image_path" not in item or not str(item["image_path"]).strip():
            raise ManifestValidationError(f"Probe entry #{idx} is missing required 'image_path'")

        probe_id = str(item["probe_id"]).strip()
        img_path = _resolve_file_path(str(item["image_path"]), base_dir)
        if validate_files and not img_path.is_file():
            raise SampleNotFoundError(
                f"Probe image for probe '{probe_id}' not found at: {img_path}"
            )

        is_live = bool(item.get("is_live", True))
        attack_type = item.get("attack_type")
        if not is_live and not attack_type:
            attack_type = "unspecified_spoof"

        expected_id = item.get("expected_identity")
        if expected_id is not None:
            expected_id = str(expected_id).strip()
            if not expected_id:
                expected_id = None

        probes.append(
            ProbeRecord(
                probe_id=probe_id,
                image_path=img_path,
                expected_identity=expected_id,
                is_live=is_live,
                attack_type=attack_type,
                metadata=item.get("metadata", {}),
            )
        )

    return BenchmarkManifest(
        name=name,
        description=description,
        gallery=gallery,
        probes=probes,
        manifest_path=path,
    )


def _load_csv_manifest(
    path: Path, base_dir: Path, validate_files: bool
) -> BenchmarkManifest:
    gallery: list[GalleryRecord] = []
    probes: list[ProbeRecord] = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                record_type = row.get("type", "").strip().lower()
                if record_type == "gallery":
                    person_id = row.get("person_id", "").strip()
                    img_path_str = row.get("image_path", "").strip()
                    if not person_id or not img_path_str:
                        raise ManifestValidationError(
                            f"CSV Row {idx}: gallery record requires 'person_id' and 'image_path'"
                        )
                    resolved = _resolve_file_path(img_path_str, base_dir)
                    if validate_files and not resolved.is_file():
                        raise SampleNotFoundError(f"Gallery file not found: {resolved}")
                    gallery.append(GalleryRecord(person_id=person_id, image_path=resolved))
                elif record_type == "probe":
                    probe_id = row.get("probe_id", f"P_{idx}").strip()
                    img_path_str = row.get("image_path", "").strip()
                    if not img_path_str:
                        raise ManifestValidationError(
                            f"CSV Row {idx}: probe record requires 'image_path'"
                        )
                    resolved = _resolve_file_path(img_path_str, base_dir)
                    if validate_files and not resolved.is_file():
                        raise SampleNotFoundError(f"Probe file not found: {resolved}")
                    
                    is_live_str = row.get("is_live", "true").strip().lower()
                    is_live = is_live_str in ("true", "1", "yes")
                    attack_type = row.get("attack_type", "").strip() or None
                    expected_id = row.get("expected_identity", "").strip() or None

                    probes.append(
                        ProbeRecord(
                            probe_id=probe_id,
                            image_path=resolved,
                            expected_identity=expected_id,
                            is_live=is_live,
                            attack_type=attack_type,
                        )
                    )
                else:
                    raise ManifestValidationError(
                        f"CSV Row {idx}: unknown record type '{record_type}'. Expected 'gallery' or 'probe'."
                    )
    except Exception as exc:
        if isinstance(exc, (ManifestValidationError, SampleNotFoundError)):
            raise
        raise ManifestValidationError(f"Failed parsing CSV manifest {path}: {exc}") from exc

    return BenchmarkManifest(
        name=path.stem,
        description=f"Loaded from CSV {path.name}",
        gallery=gallery,
        probes=probes,
        manifest_path=path,
    )
