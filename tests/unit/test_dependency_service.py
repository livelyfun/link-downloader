"""Unit tests for DependencyService and FfmpegService detection."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from link_downloader.services.dependency_service import DependencyService
from link_downloader.services.ffmpeg_service import FfmpegService


def test_dependency_service_checks_all_categories() -> None:
    svc = DependencyService()
    statuses = svc.check_all()
    names = {s.name: s for s in statuses}
    assert "PySide6 (Qt 6)" in names
    assert "HTTPX" in names
    assert "yt-dlp Python API" in names
    assert "yt-dlp-ejs" in names
    assert "FFmpeg" in names
    assert names["PySide6 (Qt 6)"].available is True
    assert names["HTTPX"].available is True
    assert names["yt-dlp Python API"].available is True
    assert names["yt-dlp-ejs"].available is True


def test_ffmpeg_service_handles_missing_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(Path, "is_file", lambda _self: False)
    ff = FfmpegService()
    assert ff.find_ffmpeg() is None
    assert ff.is_ffmpeg_available() is False


def test_js_runtime_config_dict_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = DependencyService()
    monkeypatch.setattr(svc, "_find_js_runtime", lambda: ("node", "/usr/bin/node", "24.0.0", True))
    cfg = svc.get_ytdlp_js_runtimes()
    assert cfg == {"node": {"path": "/usr/bin/node"}}
