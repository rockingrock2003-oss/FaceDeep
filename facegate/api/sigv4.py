"""Server-side verification of AWS Signature Version 4.

The attendance app signs every Rekognition request with an access key and
secret (via the AWS SDK). We verify the signature the same way AWS does, so
the app keeps its SDK, its signing code and its security model; only the
endpoint URL and the credentials change.

Reference: https://docs.aws.amazon.com/IAM/latest/UserGuide/create-signed-request.html
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, unquote

_AUTH_RE = re.compile(
    r"^AWS4-HMAC-SHA256\s+"
    r"Credential=(?P<cred>[^,\s]+),\s*"
    r"SignedHeaders=(?P<signed>[^,\s]+),\s*"
    r"Signature=(?P<sig>[0-9a-f]{64})\s*$"
)


class SignatureError(Exception):
    def __init__(self, code: str, message: str, status: int = 403):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class Principal:
    access_key_id: str
    region: str
    service: str


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    k = _hmac(("AWS4" + secret).encode(), date)
    k = _hmac(k, region)
    k = _hmac(k, service)
    return _hmac(k, "aws4_request")


def _canonical_query(query: str) -> str:
    if not query:
        return ""
    params = []
    for part in query.split("&"):
        if not part:
            continue
        k, _, v = part.partition("=")
        params.append((quote(unquote(k), safe="-_.~"), quote(unquote(v), safe="-_.~")))
    params.sort()
    return "&".join(f"{k}={v}" for k, v in params)


def _canonical_uri(path: str) -> str:
    # AWS normalises and URI-encodes each segment once for non-S3 services.
    return quote(path or "/", safe="/-_.~")


def verify(
    *,
    method: str,
    path: str,
    query: str,
    headers: dict[str, str],
    body: bytes,
    credentials: dict[str, str],
    max_skew_seconds: int = 300,
    now: datetime | None = None,
) -> Principal:
    """Raise SignatureError unless the request carries a valid SigV4 signature."""
    h = {k.lower(): v for k, v in headers.items()}
    auth = h.get("authorization")
    if not auth:
        raise SignatureError("MissingAuthenticationTokenException", "Missing Authentication Token", 400)
    m = _AUTH_RE.match(auth.strip())
    if not m:
        raise SignatureError("IncompleteSignatureException", "Authorization header is malformed", 400)

    cred_parts = m["cred"].split("/")
    if len(cred_parts) != 5 or cred_parts[4] != "aws4_request":
        raise SignatureError("IncompleteSignatureException", "Credential scope is malformed", 400)
    access_key, date, region, service, _ = cred_parts

    secret = credentials.get(access_key)
    if secret is None:
        raise SignatureError(
            "UnrecognizedClientException", "The security token included in the request is invalid.", 400
        )

    amz_date = h.get("x-amz-date")
    if not amz_date:
        raise SignatureError("IncompleteSignatureException", "x-amz-date header is required", 400)
    try:
        ts = datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise SignatureError("IncompleteSignatureException", "x-amz-date is malformed", 400) from exc
    if not amz_date.startswith(date):
        raise SignatureError("SignatureDoesNotMatch", "Credential date does not match x-amz-date")
    current = now or datetime.now(UTC)
    if abs((current - ts).total_seconds()) > max_skew_seconds:
        raise SignatureError(
            "InvalidSignatureException",
            "Signature expired: request timestamp is outside the allowed clock skew.",
        )

    signed_headers = m["signed"].split(";")
    if "host" not in signed_headers:
        raise SignatureError("IncompleteSignatureException", "The host header must be signed", 400)
    canon_headers = ""
    for name in signed_headers:
        if name not in h:
            raise SignatureError("IncompleteSignatureException", f"Signed header {name} is missing", 400)
        value = " ".join(h[name].strip().split())
        canon_headers += f"{name}:{value}\n"

    payload_hash = h.get("x-amz-content-sha256") or hashlib.sha256(body).hexdigest()
    if payload_hash != "UNSIGNED-PAYLOAD" and payload_hash != hashlib.sha256(body).hexdigest():
        raise SignatureError("SignatureDoesNotMatch", "Payload hash does not match the body")

    canonical_request = "\n".join(
        [
            method.upper(),
            _canonical_uri(path),
            _canonical_query(query),
            canon_headers,
            m["signed"],
            payload_hash,
        ]
    )
    scope = f"{date}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()]
    )
    expected = hmac.new(signing_key(secret, date, region, service), string_to_sign.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, m["sig"]):
        raise SignatureError(
            "InvalidSignatureException",
            "The request signature we calculated does not match the signature you provided. "
            "Check your AWS Secret Access Key and signing method.",
        )
    return Principal(access_key_id=access_key, region=region, service=service)
