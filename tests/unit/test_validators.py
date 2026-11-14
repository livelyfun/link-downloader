"""Unit tests for URL normalization and basic validation."""

from __future__ import annotations

import pytest

from link_downloader.core.exceptions import UnsafeUrlError, ValidationError
from link_downloader.core.validators import normalize_and_validate_url


def test_valid_https_and_http_normalization() -> None:
    assert (
        normalize_and_validate_url("  HTTPS://EXAMPLE.COM/path/video.mp4  ", strict_dns=False)
        == "https://example.com/path/video.mp4"
    )
    assert (
        normalize_and_validate_url("http://Example.Org", strict_dns=False)
        == "http://example.org/"
    )
    assert (
        normalize_and_validate_url(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ#t=10", strict_dns=False
        )
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )


@pytest.mark.parametrize(
    "bad_url",
    [
        "",
        "   ",
        "not-a-url",
        "example.com/file.zip",
        "https:///no-host.mp4",
        "https://example.com:99999/test",
        "https://example.com/has space.mp4",
        "https://example.com/ctrl\nchar",
    ],
)
def test_rejects_malformed_urls(bad_url: str) -> None:
    with pytest.raises(ValidationError):
        normalize_and_validate_url(bad_url, strict_dns=False)


def test_rejects_embedded_credentials() -> None:
    with pytest.raises(UnsafeUrlError):
        normalize_and_validate_url("https://user:secret@example.com/file.zip", strict_dns=False)
