"""Security tests covering SSRF, unsafe protocols, redirects, and path traversal."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from link_downloader.core.enums import OverwriteBehavior
from link_downloader.core.exceptions import RedirectBlockedError, UnsafeUrlError, ValidationError
from link_downloader.core.validators import normalize_and_validate_url, validate_redirect_url
from link_downloader.services.file_service import (
    parse_content_disposition,
    resolve_collision_safe_path,
    sanitize_filename,
)


@pytest.mark.security
@pytest.mark.parametrize(
    "unsafe_url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://ftp.example.com/file.zip",
        "vbscript:msgbox(1)",
    ],
)
def test_blocks_unsafe_protocols(unsafe_url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        normalize_and_validate_url(unsafe_url, strict_dns=False)


@pytest.mark.security
@pytest.mark.parametrize(
    "internal_url",
    [
        "http://localhost/admin",
        "http://sub.localhost:8080/api",
        "http://127.0.0.1/secret",
        "http://127.0.1.1:9000/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0:8000/",
        "http://10.0.0.1/internal",
        "http://172.16.5.4/metrics",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://printer.local/status",
    ],
)
def test_blocks_localhost_private_and_metadata_addresses(internal_url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        normalize_and_validate_url(internal_url, strict_dns=False)


@pytest.mark.security
def test_blocks_dns_rebinding_to_private_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host, port, type=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.10.20", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError):
        normalize_and_validate_url("https://rebind-attacker.example/file.mp4", strict_dns=True)


@pytest.mark.security
@pytest.mark.parametrize(
    "redirect_target",
    [
        "http://127.0.0.1:8080/internal",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.20.30.40/secret",
        "http://localhost/admin",
        "file:///etc/shadow",
        "javascript:alert(1)",
    ],
)
def test_blocks_unsafe_redirect_targets(redirect_target: str) -> None:
    with pytest.raises(RedirectBlockedError):
        validate_redirect_url(
            redirect_target,
            "https://public.example.com/start",
            strict_dns=False,
        )


@pytest.mark.security
@pytest.mark.parametrize(
    "malicious_name",
    [
        "../../etc/passwd",
        "..\\..\\Windows\\System32\\cmd.exe",
        "/etc/shadow",
        "foo/../../bar.mp4",
        "evil\x00file.mp4",
        "...",
    ],
)
def test_sanitize_filename_prevents_traversal(malicious_name: str) -> None:
    cleaned = sanitize_filename(malicious_name)
    assert "/" not in cleaned
    assert "\\" not in cleaned
    assert ".." not in cleaned
    assert "\x00" not in cleaned
    assert cleaned not in {".", ".."}


@pytest.mark.security
@pytest.mark.parametrize("reserved", ["CON.mp4", "PRN.txt", "AUX", "NUL.zip", "COM1.log", "LPT9.bin"])
def test_sanitize_filename_guards_windows_reserved_names(reserved: str) -> None:
    cleaned = sanitize_filename(reserved)
    stem = Path(cleaned).stem.upper()
    assert stem not in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT9"}


@pytest.mark.security
def test_content_disposition_traversal_stripped() -> None:
    header = 'attachment; filename="../../../etc/cron.d/pwn.sh"'
    assert parse_content_disposition(header) == "pwn.sh"


@pytest.mark.security
def test_resolve_collision_safe_path_stays_inside_directory(tmp_path: Path) -> None:
    out_dir = tmp_path / "downloads"
    resolved = resolve_collision_safe_path(
        out_dir,
        "../../outside_secret.txt",
        OverwriteBehavior.RENAME,
    )
    assert resolved.parent == out_dir.resolve()
    assert resolved.is_relative_to(out_dir.resolve())
    assert resolved.name == "outside_secret.txt"


@pytest.mark.security
def test_normalize_rejects_excessive_length() -> None:
    long_url = "https://example.com/" + ("a" * 5000)
    with pytest.raises(ValidationError):
        normalize_and_validate_url(long_url, strict_dns=False)
