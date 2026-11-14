"""Unit tests for file naming, MIME mapping, Content-Disposition, and collision handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from link_downloader.core.enums import OverwriteBehavior
from link_downloader.core.exceptions import FileCollisionError
from link_downloader.services.file_service import (
    classify_file_category,
    detect_extension_from_mime,
    infer_filename_from_url,
    parse_content_disposition,
    resolve_collision_safe_path,
    sanitize_filename,
)


def test_parse_content_disposition_formats() -> None:
    assert (
        parse_content_disposition("attachment; filename*=UTF-8''my%20report%202026.pdf")
        == "my report 2026.pdf"
    )
    assert parse_content_disposition('attachment; filename="archive-v2.zip"') == "archive-v2.zip"
    assert parse_content_disposition("inline") is None


def test_detect_extension_and_category() -> None:
    assert detect_extension_from_mime("video/mp4; charset=binary") == ".mp4"
    assert detect_extension_from_mime("application/pdf") == ".pdf"
    assert detect_extension_from_mime("application/octet-stream") is None
    assert classify_file_category(".mp4") == "Video"
    assert classify_file_category(".mp3") == "Audio"
    assert classify_file_category(".png") == "Image"
    assert classify_file_category(".pdf") == "Document"
    assert classify_file_category(".zip") == "Archive"
    assert classify_file_category(".deb") == "Software Package"


def test_infer_filename_extensionless_with_mime() -> None:
    name = infer_filename_from_url(
        "https://cdn.example.com/download?id=42",
        content_disposition=None,
        content_type="application/pdf",
    )
    assert name == "download.pdf"


def test_sanitize_preserves_extension_when_truncating() -> None:
    long_title = ("x" * 250) + ".mp4"
    result = sanitize_filename(long_title, max_length=120)
    assert len(result) <= 120
    assert result.endswith(".mp4")


def test_collision_resolution_policies(tmp_path: Path) -> None:
    existing = tmp_path / "demo.mp4"
    existing.write_bytes(b"abc")

    renamed = resolve_collision_safe_path(tmp_path, "demo.mp4", OverwriteBehavior.RENAME)
    assert renamed.name == "demo (1).mp4"

    # Also honors active in-memory queue reservations
    reserved = {renamed}
    renamed_2 = resolve_collision_safe_path(
        tmp_path,
        "demo.mp4",
        OverwriteBehavior.RENAME,
        reserved_paths=reserved,
    )
    assert renamed_2.name == "demo (2).mp4"

    overwritten = resolve_collision_safe_path(tmp_path, "demo.mp4", OverwriteBehavior.OVERWRITE)
    assert overwritten == existing.resolve()

    with pytest.raises(FileCollisionError):
        resolve_collision_safe_path(tmp_path, "demo.mp4", OverwriteBehavior.SKIP)
