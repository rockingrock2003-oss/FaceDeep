import hashlib
import io
import logging
from pathlib import Path

from PIL import Image, ExifTags

logger = logging.getLogger("facedeep.image_processor")

# Magic bytes for supported image formats
MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # WebP starts with RIFF
    b"BM": "image/bmp",
}

MAX_RESOLUTION = (4096, 4096)
SUPPORTED_FORMATS = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
FORMAT_MAP = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP", "image/bmp": "BMP"}


def detect_format(data: bytes) -> str | None:
    for magic, mime in MAGIC_BYTES.items():
        if data[: len(magic)] == magic:
            return mime
    return None


def validate_image(data: bytes, max_size_bytes: int = 10 * 1024 * 1024) -> str | None:
    if len(data) > max_size_bytes:
        raise ValueError(f"Image exceeds maximum size of {max_size_bytes} bytes")
    fmt = detect_format(data)
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported image format: {fmt}. Supported: {SUPPORTED_FORMATS}")
    return fmt


def strip_exif(img: Image.Image) -> Image.Image:
    data = list(img.getdata())
    clean = Image.new(img.mode, img.size)
    clean.putdata(data)
    return clean


def downscale_if_needed(img: Image.Image, max_res: tuple[int, int] = MAX_RESOLUTION) -> Image.Image:
    w, h = img.size
    max_w, max_h = max_res
    if w <= max_w and h <= max_h:
        return img
    ratio = min(max_w / w, max_h / h)
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    return img.resize((new_w, new_h), Image.LANCZOS)


def process_image(
    data: bytes,
    target_format: str = "WEBP",
    quality: int = 85,
    max_res: tuple[int, int] = MAX_RESOLUTION,
    strip_exif_data: bool = True,
) -> tuple[bytes, dict]:
    source_format = validate_image(data)
    img = Image.open(io.BytesIO(data))

    if strip_exif_data:
        img = strip_exif(img)

    img = downscale_if_needed(img, max_res)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    out_fmt = FORMAT_MAP.get(target_format, "WEBP")
    buf = io.BytesIO()
    save_kwargs = {"format": out_fmt, "quality": quality, "optimize": True}
    if out_fmt == "WEBP":
        save_kwargs["method"] = 6
    img.save(buf, **save_kwargs)
    processed = buf.getvalue()

    info = {
        "source_format": source_format,
        "target_format": target_format,
        "original_size": len(data),
        "processed_size": len(processed),
        "original_dimensions": f"{img.size[0]}x{img.size[1]}",
        "processing_ratio": round(len(processed) / len(data), 3) if len(data) > 0 else 0,
        "hash": hashlib.sha256(processed).hexdigest(),
    }
    return processed, info
