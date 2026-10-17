"""Resolve Rekognition ``Image`` parameters to decoded pixels.

``Image`` is either ``{"Bytes": <base64>}`` or ``{"S3Object": {...}}``. Bytes
are what a mobile/kiosk attendance flow sends. S3Object is supported when the
service is given S3 (or S3-compatible, e.g. MinIO) credentials.
"""

from __future__ import annotations

import base64
import binascii

import numpy as np

from facegate.api import errors
from facegate.config import Settings
from facegate.engine.pipeline import ImageDecodeError, decode_image

_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"


def _fetch_s3(obj: dict) -> bytes:
    try:
        import boto3  # optional dependency
    except ImportError as exc:  # pragma: no cover
        raise errors.InvalidS3ObjectException("S3 access is not configured on this server") from exc
    bucket, name = obj.get("Bucket"), obj.get("Name")
    if not bucket or not name:
        raise errors.InvalidParameterException("S3Object requires Bucket and Name")
    kwargs = {"Bucket": bucket, "Key": name}
    if obj.get("Version"):
        kwargs["VersionId"] = obj["Version"]
    try:
        return boto3.client("s3").get_object(**kwargs)["Body"].read()
    except Exception as exc:
        raise errors.InvalidS3ObjectException(f"Unable to get object metadata from S3. Check object key, region and/or access permissions. ({type(exc).__name__})") from exc


def image_bytes(image: dict | None, settings: Settings, field: str = "Image") -> bytes:
    if not isinstance(image, dict):
        raise errors.InvalidParameterException(f"{field} is required")
    if "Bytes" in image:
        try:
            data = base64.b64decode(image["Bytes"], validate=True)
        except (binascii.Error, TypeError) as exc:
            raise errors.InvalidImageFormatException("Request has invalid image format") from exc
    elif "S3Object" in image:
        data = _fetch_s3(image["S3Object"])
    else:
        raise errors.InvalidParameterException(f"{field} must contain Bytes or S3Object")
    if len(data) > settings.max_image_bytes:
        raise errors.ImageTooLargeException("Image size is too large.")
    if not (data.startswith(_JPEG) or data.startswith(_PNG)):
        raise errors.InvalidImageFormatException("Request has invalid image format")
    return data


def load_image(image: dict | None, settings: Settings, field: str = "Image") -> tuple[np.ndarray, bytes]:
    data = image_bytes(image, settings, field)
    try:
        img = decode_image(data)
    except ImageDecodeError as exc:
        raise errors.InvalidImageFormatException("Request has invalid image format") from exc
    h, w = img.shape[:2]
    if min(h, w) < settings.min_image_side:
        raise errors.InvalidParameterException(
            f"Image dimensions must be at least {settings.min_image_side} pixels"
        )
    return img, data
