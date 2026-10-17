"""Download the face models and verify their checksums.

| model                               | role                     | licence    |
|-------------------------------------|--------------------------|------------|
| face_detection_yunet_2023mar.onnx   | face detection           | MIT        |
| face_recognition_sface_2021dec.onnx | face templates (128-d)   | Apache-2.0 |
| MiniFASNetV2 / MiniFASNetV1SE .onnx | passive anti-spoofing    | Apache-2.0 |

The MiniFASNet ONNX files are ONNX exports of the Silent-Face-Anti-Spoofing
weights (minivision-ai) and ship in the repository; the others come from the
OpenCV Zoo.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
    "MiniFASNetV2.onnx": (None, "b32929adc2d9c34b9486f8c4c7bc97c1b69bc0ea9befefc380e4faae4e463907"),
    "MiniFASNetV1SE.onnx": (None, "ebab7f90c7833fbccd46d3a555410e78d969db5438e169b6524be444862b3676"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(dest: Path = Path(__file__).resolve().parent.parent / "models") -> int:
    dest.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, (url, digest) in MODELS.items():
        path = dest / name
        if not path.exists() and url:
            print(f"downloading {name} ...")
            urllib.request.urlretrieve(url, path)
        if not path.exists():
            print(f"MISSING  {name}")
            ok = False
            continue
        actual = sha256(path)
        status = "OK      " if actual == digest else "MISMATCH"
        ok &= actual == digest
        print(f"{status} {name}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
