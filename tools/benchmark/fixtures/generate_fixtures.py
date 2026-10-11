from __future__ import annotations

import json
from pathlib import Path
import cv2
import numpy as np

FIXTURES_DIR = Path(__file__).resolve().parent
DATASET_DIR = FIXTURES_DIR / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)

SOURCE_IMG = Path("/home/izzath/Documents/Dev/FaceDeep/.venv/lib/python3.11/site-packages/insightface/data/images/t1.jpg")


def crop_face(img: np.ndarray, bbox: list[float], margin: float = 0.5) -> np.ndarray:
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    size = max(w, h) * (1.0 + margin)

    nx1 = max(0, int(cx - size / 2.0))
    ny1 = max(0, int(cy - size / 2.0))
    nx2 = min(img.shape[1], int(cx + size / 2.0))
    ny2 = min(img.shape[0], int(cy + size / 2.0))

    return img[ny1:ny2, nx1:nx2]


def main() -> None:
    if not SOURCE_IMG.exists():
        print(f"Source image not found at {SOURCE_IMG}")
        return

    img = cv2.imread(str(SOURCE_IMG))

    # Bboxes from detection
    # Face 0: [466.08, 268.61, 573.58, 415.53] (EMP001)
    # Face 1: [745.35, 338.74, 845.66, 479.09] (EMP002)
    # Face 2: [268.49, 145.60, 372.32, 267.00] (IMPOSTOR)
    f0_crop = crop_face(img, [466.08, 268.61, 573.58, 415.53])
    f1_crop = crop_face(img, [745.35, 338.74, 845.66, 479.09])
    f2_crop = crop_face(img, [268.49, 145.60, 372.32, 267.00])

    # 1. Gallery
    emp1_gal_path = DATASET_DIR / "EMP001_gallery.jpg"
    emp2_gal_path = DATASET_DIR / "EMP002_gallery.jpg"
    cv2.imwrite(str(emp1_gal_path), cv2.resize(f0_crop, (300, 300)))
    cv2.imwrite(str(emp2_gal_path), cv2.resize(f1_crop, (300, 300)))

    # 2. Genuine Live Probes (slight scale & brightness variation)
    emp1_probe_path = DATASET_DIR / "EMP001_probe_live.jpg"
    emp2_probe_path = DATASET_DIR / "EMP002_probe_live.jpg"
    f0_probe = cv2.convertScaleAbs(f0_crop, alpha=1.03, beta=5)
    f1_probe = cv2.convertScaleAbs(f1_crop, alpha=0.98, beta=-4)
    cv2.imwrite(str(emp1_probe_path), cv2.resize(f0_probe, (300, 300)))
    cv2.imwrite(str(emp2_probe_path), cv2.resize(f1_probe, (300, 300)))

    # 3. Impostor Live Probe (Face 2, not enrolled)
    impostor_probe_path = DATASET_DIR / "IMPOSTOR_probe_live.jpg"
    cv2.imwrite(str(impostor_probe_path), cv2.resize(f2_crop, (300, 300)))

    # 4. Spoof Attack Probe (Print attack simulation with low contrast and heavy blur / moire)
    spoof_probe_path = DATASET_DIR / "EMP001_probe_spoof_print.jpg"
    f0_spoof = cv2.GaussianBlur(f0_crop, (15, 15), 0)
    # Add flat paper white border
    h, w = f0_spoof.shape[:2]
    f0_spoof_bordered = cv2.copyMakeBorder(f0_spoof, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    cv2.imwrite(str(spoof_probe_path), cv2.resize(f0_spoof_bordered, (300, 300)))

    # 5. Invalid Non-Face Image (blank / texture to test clear error handling)
    corrupt_path = DATASET_DIR / "corrupt_no_face.jpg"
    noise_img = np.full((300, 300, 3), 128, dtype=np.uint8)
    cv2.imwrite(str(corrupt_path), noise_img)

    # 6. Generate manifest.json
    manifest_data = {
        "name": "FaceDeep-Local-Fixture-v1",
        "description": "Deterministic local test fixture dataset containing 2 gallery identities, genuine live probes, unenrolled impostor probe, and presentation attack probe.",
        "gallery": [
            {
                "person_id": "EMP001",
                "image_path": "dataset/EMP001_gallery.jpg",
                "metadata": {"department": "Engineering", "role": "Systems Engineer"}
            },
            {
                "person_id": "EMP002",
                "image_path": "dataset/EMP002_gallery.jpg",
                "metadata": {"department": "Operations", "role": "Site Reliability Engineer"}
            }
        ],
        "probes": [
            {
                "probe_id": "PROBE_EMP001_LIVE",
                "image_path": "dataset/EMP001_probe_live.jpg",
                "expected_identity": "EMP001",
                "is_live": True,
                "attack_type": None,
                "metadata": {"lighting": "normal"}
            },
            {
                "probe_id": "PROBE_EMP002_LIVE",
                "image_path": "dataset/EMP002_probe_live.jpg",
                "expected_identity": "EMP002",
                "is_live": True,
                "attack_type": None,
                "metadata": {"lighting": "normal"}
            },
            {
                "probe_id": "PROBE_IMPOSTOR_LIVE",
                "image_path": "dataset/IMPOSTOR_probe_live.jpg",
                "expected_identity": None,
                "is_live": True,
                "attack_type": None,
                "metadata": {"lighting": "normal"}
            },
            {
                "probe_id": "PROBE_EMP001_SPOOF_PRINT",
                "image_path": "dataset/EMP001_probe_spoof_print.jpg",
                "expected_identity": "EMP001",
                "is_live": False,
                "attack_type": "level1_print",
                "metadata": {"medium": "matte_paper_photo"}
            },
            {
                "probe_id": "PROBE_CORRUPT_NO_FACE",
                "image_path": "dataset/corrupt_no_face.jpg",
                "expected_identity": None,
                "is_live": True,
                "attack_type": None,
                "metadata": {"expected_failure": True}
            }
        ]
    }

    manifest_file = FIXTURES_DIR / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print(f"Generated fixture dataset at: {DATASET_DIR}")
    print(f"Generated fixture manifest at: {manifest_file}")


if __name__ == "__main__":
    main()
