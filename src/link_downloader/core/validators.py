"""URL validation, normalization, and SSRF / private-network safeguards."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

from link_downloader.core.exceptions import RedirectBlockedError, UnsafeUrlError, ValidationError

ALLOWED_SCHEMES = frozenset({"http", "https"})
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
        "metadata",
    }
)
BLOCKED_HOSTNAME_SUFFIXES = (".localhost", ".local", ".internal")
MAX_URL_LENGTH = 4096


def is_unsafe_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP address belongs to loopback, private, link-local, or reserved space."""
    if (
        isinstance(ip_obj, ipaddress.IPv6Address)
        and ip_obj.ipv4_mapped is not None
        and is_unsafe_ip(ip_obj.ipv4_mapped)
    ):
        return True

    return bool(
        ip_obj.is_loopback
        or ip_obj.is_private
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
        or not ip_obj.is_global
    )


def _strip_ipv6_zone(hostname: str) -> str:
    """Remove IPv6 zone identifier (e.g. %eth0) if present."""
    if "%" in hostname:
        return hostname.split("%", 1)[0]
    return hostname


def verify_hostname_safety(
    hostname: str,
    port: int,
    *,
    allow_private: bool = False,
    strict_dns: bool = False,
) -> None:
    """Validate that a hostname is neither a local alias nor resolves to an unsafe IP."""
    lowered = hostname.strip().rstrip(".").lower()
    if not lowered:
        raise ValidationError("URL is missing a valid hostname.")

    if allow_private:
        return

    if lowered in BLOCKED_HOSTNAMES or lowered.endswith(BLOCKED_HOSTNAME_SUFFIXES):
        raise UnsafeUrlError(
            f"Blocked access to local or internal host '{hostname}'.",
        )

    cleaned_host = _strip_ipv6_zone(lowered)
    try:
        ip_obj = ipaddress.ip_address(cleaned_host)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        if is_unsafe_ip(ip_obj):
            raise UnsafeUrlError(
                f"Blocked access to non-public IP address '{ip_obj}'.",
            )
        return

    # Perform DNS resolution check to catch domains pointing to internal/loopback/metadata IPs
    try:
        addr_infos = socket.getaddrinfo(cleaned_host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        if strict_dns:
            raise ValidationError(
                f"Could not resolve hostname '{hostname}'.",
                details=str(exc),
            ) from exc
        return

    for info in addr_infos:
        sockaddr = info[4]
        raw_ip = _strip_ipv6_zone(str(sockaddr[0]))
        try:
            resolved_ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        if is_unsafe_ip(resolved_ip):
            raise UnsafeUrlError(
                f"Host '{hostname}' resolves to blocked non-public IP '{resolved_ip}'.",
            )


def normalize_and_validate_url(
    raw_url: str,
    *,
    allow_private: bool = False,
    strict_dns: bool = False,
) -> str:
    """Validate and normalize an untrusted HTTP/HTTPS URL string."""
    if not isinstance(raw_url, str):
        raise ValidationError("URL must be a text string.")

    cleaned = raw_url.strip()
    if not cleaned:
        raise ValidationError("Please enter a URL.")

    if len(cleaned) > MAX_URL_LENGTH:
        raise ValidationError("URL exceeds maximum allowed length.")

    if any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
        raise ValidationError("URL contains invalid control characters.")

    if any(ch.isspace() for ch in cleaned):
        raise ValidationError("URL contains unexpected whitespace characters.")

    parsed = urlsplit(cleaned)
    scheme = parsed.scheme.lower()
    if not scheme:
        raise ValidationError("URL must include http:// or https://.")

    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(
            f"Unsupported or unsafe protocol '{scheme}://'. Only http:// and https:// URLs are permitted.",
        )

    if not parsed.netloc or not parsed.hostname:
        raise ValidationError("URL is missing a valid domain or host.")

    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("URLs containing embedded credentials are not permitted.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("URL specifies an invalid port number.") from exc

    if port is not None and not (1 <= port <= 65535):
        raise ValidationError("URL port number must be between 1 and 65535.")

    effective_port = port or (443 if scheme == "https" else 80)
    verify_hostname_safety(
        parsed.hostname,
        effective_port,
        allow_private=allow_private,
        strict_dns=strict_dns,
    )

    hostname_ascii = parsed.hostname
    if ":" in hostname_ascii and not hostname_ascii.startswith("["):
        netloc_host = f"[{hostname_ascii}]"
    else:
        netloc_host = hostname_ascii.lower()

    normalized_netloc = f"{netloc_host}:{port}" if port is not None else netloc_host
    normalized_path = parsed.path or "/"
    return urlunsplit((scheme, normalized_netloc, normalized_path, parsed.query, ""))


def validate_redirect_url(
    target_url: str,
    current_url: str,
    *,
    allow_private: bool = False,
    strict_dns: bool = False,
) -> str:
    """Resolve and validate an HTTP redirect target against SSRF and protocol rules."""
    if not isinstance(target_url, str) or not target_url.strip():
        raise RedirectBlockedError("Server returned an empty redirect location.")

    resolved = urljoin(current_url, target_url.strip())
    try:
        return normalize_and_validate_url(
            resolved,
            allow_private=allow_private,
            strict_dns=strict_dns,
        )
    except ValidationError as exc:
        raise RedirectBlockedError(
            f"Blocked redirect to unsafe or invalid destination: {exc.message}",
            details=exc.details,
        ) from exc
