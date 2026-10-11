import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


def validate_http_url_syntax(url: str, *, https_only: bool = False) -> str:
    parsed = urlsplit(url)
    allowed_schemes = {"https"} if https_only else {"http", "https"}

    if parsed.scheme.lower() not in allowed_schemes:
        required = "HTTPS" if https_only else "HTTP or HTTPS"
        raise ValueError(f"URL must use {required}")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed")
    if parsed.fragment:
        raise ValueError("URL fragments are not allowed")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Localhost URLs are not allowed")

    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise ValueError("URL contains an invalid port") from exc

    if parsed_port is not None and not 1 <= parsed_port <= 65535:
        raise ValueError("URL contains an invalid port")

    return url


def _is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_global


def _resolve_host(hostname: str, port: int) -> set[str]:
    addresses: set[str] = set()
    for family, _, _, _, sockaddr in socket.getaddrinfo(
        hostname,
        port,
        type=socket.SOCK_STREAM,
    ):
        if family == socket.AF_INET:
            addresses.add(sockaddr[0])
        elif family == socket.AF_INET6:
            addresses.add(sockaddr[0])
    return addresses


async def validate_public_http_url(url: str, *, https_only: bool = False) -> str:
    validate_http_url_syntax(url, https_only=https_only)
    parsed = urlsplit(url)
    hostname = parsed.hostname
    assert hostname is not None

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if not literal_ip.is_global:
            raise ValueError("URL resolves to a non-public network address")
        return url

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        addresses = await asyncio.to_thread(_resolve_host, hostname, port)
    except socket.gaierror as exc:
        raise ValueError("URL hostname could not be resolved") from exc

    if not addresses:
        raise ValueError("URL hostname did not resolve to an address")
    if any(not _is_public_ip(address) for address in addresses):
        raise ValueError("URL resolves to a non-public network address")

    return url
