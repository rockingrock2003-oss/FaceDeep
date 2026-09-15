import re
import logging
from datetime import datetime, timezone

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("facedeep.versioning")

# Supported API versions in order (newest first)
SUPPORTED_VERSIONS = ["v1", "v2"]
LATEST_VERSION = "v2"

# Deprecation sunset dates per version
SUNSET_DATES = {
    "v1": datetime(2027, 3, 15, tzinfo=timezone.utc),
}

# Docs URLs per version
VERSION_DOCS = {
    "v1": "https://docs.facedeep.com/api/v1",
    "v2": "https://docs.facedeep.com/api/v2",
}

# Accept header pattern: application/vnd.facedeep.v2+json
ACCEPT_PATTERN = re.compile(
    r"application/vnd\.facedeep\.(v\d+)\+json", re.IGNORECASE
)


def extract_version_from_accept(accept_header: str) -> str | None:
    """Extract API version from Accept header.

    Supports:
      - application/vnd.facedeep.v1+json
      - application/vnd.facedeep.v2+json
    """
    if not accept_header:
        return None
    for part in accept_header.split(","):
        part = part.strip()
        m = ACCEPT_PATTERN.match(part)
        if m:
            version = m.group(1)
            if version in SUPPORTED_VERSIONS:
                return version
    return None


def extract_version_from_path(path: str) -> str | None:
    """Extract version from URL path like /api/v1/... or /api/v2/..."""
    m = re.match(r"^/api/(v\d+)/", path)
    if m:
        version = m.group(1)
        if version in SUPPORTED_VERSIONS:
            return version
    return None


class APIVersioningMiddleware(BaseHTTPMiddleware):
    """Middleware that:
    1. Adds deprecation headers to deprecated API versions
    2. Supports version negotiation via Accept header
    3. Adds API-Version response header
    """

    async def dispatch(self, request: Request, call_next):
        # Determine version from URL path
        path_version = extract_version_from_path(request.url.path)

        # Check Accept header for version negotiation
        accept_header = request.headers.get("Accept", "")
        negotiated_version = extract_version_from_accept(accept_header)

        # If Accept header requests a specific version but URL is different,
        # log a warning (we route by URL, not by Accept header)
        if negotiated_version and path_version and negotiated_version != path_version:
            logger.info(
                f"Accept header requests {negotiated_version} but URL is {path_version}; "
                f"using URL version"
            )

        # Use URL version as the resolved version
        resolved_version = path_version or negotiated_version or LATEST_VERSION

        response = await call_next(request)

        # Add version header to all API responses
        response.headers["API-Version"] = resolved_version

        # Add deprecation headers if this version is deprecated
        if resolved_version in SUNSET_DATES:
            sunset_date = SUNSET_DATES[resolved_version]
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = sunset_date.strftime("%a, %d %b %Y 00:00:00 GMT")
            response.headers["Link"] = (
                f'<{VERSION_DOCS.get(resolved_version, VERSION_DOCS["v1"])}>; '
                f'rel="deprecation"; title="API {resolved_version} is deprecated"'
            )

        # Add supported versions header
        response.headers["API-Supported-Versions"] = ", ".join(SUPPORTED_VERSIONS)
        response.headers["API-Latest-Version"] = LATEST_VERSION

        return response
