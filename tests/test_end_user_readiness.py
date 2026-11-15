"""Tests for end-user readiness: bundled package detection, one-click FFmpeg setup, and friendly UI."""

from __future__ import annotations

import importlib.metadata
import io
import os
import shutil
import sys
import tarfile
import threading
import zipfile
from pathlib import Path

import httpx
import pytest
from PySide6.QtCore import Qt

from link_downloader.config.defaults import AppSettings
from link_downloader.core.enums import DependencyCategory
from link_downloader.platform.paths import get_managed_bin_dir
from link_downloader.services.dependency_service import DependencyService, _pkg_version
from link_downloader.services.download_manager import DownloadManager
from link_downloader.services.ffmpeg_service import FfmpegService, get_ffmpeg_download_targets
from link_downloader.ui.components.dependency_banner import DependencyBanner
from link_downloader.ui.dialogs.diagnostic_dialog import DiagnosticDialog
from link_downloader.ui.dialogs.ffmpeg_prompt_dialog import FfmpegPromptDialog
from link_downloader.ui.main_window import MainWindow
from link_downloader.ui.pages.settings_page import SettingsPage


class _MissingFfmpegService(FfmpegService):
    def find_ffmpeg(self) -> str | None:
        return None

    def find_ffprobe(self) -> str | None:
        return None

    def is_ffmpeg_available(self) -> bool:
        return False


class _ReadyFfmpegService(FfmpegService):
    def find_ffmpeg(self) -> str | None:
        return "/managed/bin/ffmpeg"

    def find_ffprobe(self) -> str | None:
        return "/managed/bin/ffprobe"

    def get_version(self, binary_path: str | None) -> str | None:
        return "7.1" if binary_path else None

    def is_ffmpeg_available(self) -> bool:
        return True


def _make_mock_binary(name: str) -> bytes:
    return f"#!/bin/sh\necho '{name} version 7.1-static'\n".encode()


def _build_tar_xz_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tf:
        for arcname, payload in entries.items():
            info = tarfile.TarInfo(name=arcname)
            info.size = len(payload)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def _build_zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, payload in entries.items():
            zf.writestr(arcname, payload)
    return buf.getvalue()


def test_bundled_packages_detected_when_frozen_and_dist_info_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError("dist-info omitted in bundle")

    monkeypatch.setattr(importlib.metadata, "version", _raise_missing)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    for pkg in ("PySide6", "httpx", "yt-dlp", "yt-dlp-ejs"):
        assert _pkg_version(pkg) is not None

    svc = DependencyService(_MissingFfmpegService())
    statuses = svc.check_all()
    by_name = {s.name: s for s in statuses}

    for expected in ("PySide6 (Qt 6)", "HTTPX", "yt-dlp Python API", "yt-dlp-ejs"):
        assert by_name[expected].available is True
        assert by_name[expected].version
        assert by_name[expected].path == "Bundled inside Link Downloader"


def test_dependency_messages_have_no_cli_or_package_manager_jargon(
    isolated_app_dirs: Path,
) -> None:
    svc = DependencyService(_MissingFfmpegService())
    statuses = svc.check_all()
    report = svc.format_diagnostic_report(statuses)

    forbidden_terms = (
        "pip ",
        "apt ",
        "dnf ",
        "pacman",
        "brew ",
        "winget",
        "choco ",
        "python -c",
        "sudo ",
    )
    combined = report.lower()
    for dep in statuses:
        combined += "\n" + dep.impact.lower() + "\n" + dep.install_hint.lower() + "\n" + dep.verify_command.lower()

    for term in forbidden_terms:
        assert term not in combined, f"Found technical CLI instruction {term!r} in end-user copy"

    missing_rec = DependencyService.missing_recommended_summary(statuses)
    missing_names = {s.name for s in missing_rec}
    assert "FFmpeg" in missing_names
    assert "JavaScript Runtime (Deno / Node.js)" not in missing_names
    assert any(s.name == "JavaScript Runtime (Deno / Node.js)" and s.category == DependencyCategory.OPTIONAL for s in statuses)


def test_ffmpeg_download_targets_cover_all_supported_platforms() -> None:
    linux_x64 = get_ffmpeg_download_targets("linux", "x86_64")
    assert linux_x64[0][0] == "tar.xz"
    assert linux_x64[0][1].endswith("linux64-gpl.tar.xz")

    linux_arm = get_ffmpeg_download_targets("linux", "aarch64")
    assert linux_arm[0][1].endswith("linuxarm64-gpl.tar.xz")

    win_x64 = get_ffmpeg_download_targets("win32", "AMD64")
    assert win_x64[0][0] == "zip"
    assert win_x64[0][1].endswith("win64-gpl.zip")

    mac_arm = get_ffmpeg_download_targets("darwin", "arm64")
    assert len(mac_arm) == 2
    assert all(url.endswith(".zip") for _kind, url in mac_arm)

    mac_intel = get_ffmpeg_download_targets("darwin", "x86_64")
    assert len(mac_intel) == 2
    assert all(url.endswith(".zip") for _kind, url in mac_intel)


def test_ffmpeg_service_downloads_and_installs_tar_xz_to_user_data_dir(
    monkeypatch: pytest.MonkeyPatch,
    isolated_app_dirs: Path,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    archive_bytes = _build_tar_xz_bytes(
        {
            "ffmpeg-master/bin/ffmpeg": _make_mock_binary("ffmpeg"),
            "ffmpeg-master/bin/ffprobe": _make_mock_binary("ffprobe"),
            "ffmpeg-master/README.txt": b"readme",
        }
    )

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=archive_bytes,
            headers={"content-length": str(len(archive_bytes))},
            request=request,
        )
    )

    progress_events: list[tuple[int, str]] = []
    svc = FfmpegService()
    with httpx.Client(transport=transport) as client:
        ff_path, fp_path = svc.download_and_install(
            progress_callback=lambda pct, msg: progress_events.append((pct, msg)),
            targets=[("tar.xz", "https://example.test/ffmpeg.tar.xz")],
            client=client,
        )

    managed_dir = get_managed_bin_dir()
    assert ff_path.parent == managed_dir.resolve()
    assert fp_path is not None and fp_path.parent == managed_dir.resolve()
    assert os.access(ff_path, os.X_OK)
    assert svc.find_ffmpeg() == str(ff_path)
    assert svc.find_ffprobe() == str(fp_path)
    assert svc.is_ffmpeg_available() is True
    assert progress_events[-1] == (100, "FFmpeg is ready")


def test_ffmpeg_service_downloads_and_installs_zip_pair_and_cleans_up_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
    isolated_app_dirs: Path,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    ffmpeg_zip = _build_zip_bytes({"ffmpeg": _make_mock_binary("ffmpeg")})
    ffprobe_zip = _build_zip_bytes({"ffprobe": _make_mock_binary("ffprobe")})

    def _handler(request: httpx.Request) -> httpx.Response:
        if "ffprobe" in str(request.url):
            return httpx.Response(200, content=ffprobe_zip, request=request)
        return httpx.Response(200, content=ffmpeg_zip, request=request)

    svc = FfmpegService()
    with httpx.Client(transport=httpx.MockTransport(_handler)) as client:
        ff_path, fp_path = svc.download_and_install(
            targets=[
                ("zip", "https://example.test/ffmpeg.zip"),
                ("zip", "https://example.test/ffprobe.zip"),
            ],
            client=client,
        )

    assert ff_path.is_file()
    assert fp_path is not None and fp_path.is_file()
    assert not list(get_managed_bin_dir().glob("*.tmp"))
    assert not list(get_managed_bin_dir().glob("ffmpeg_pkg_*"))

    # Cancellation leaves clean directory
    cancel = threading.Event()
    cancel.set()
    with httpx.Client(transport=httpx.MockTransport(_handler)) as client, pytest.raises(InterruptedError):
        svc.download_and_install(
            cancel_event=cancel,
            targets=[("zip", "https://example.test/ffmpeg.zip")],
            client=client,
        )
    assert not list(get_managed_bin_dir().glob("ffmpeg_pkg_*"))


def test_ffmpeg_prompt_dialog_text_skip_and_download(
    qtbot,
    settings_manager,
    history_repo,
    isolated_app_dirs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_manager.save(AppSettings(download_folder=str(isolated_app_dirs / "downloads")))
    manager = DownloadManager(
        settings_manager=settings_manager,
        history_repo=history_repo,
        ffmpeg_service=_MissingFfmpegService(),
        dependency_service=DependencyService(_MissingFfmpegService()),
    )
    manager.startup()

    try:
        # 1. Verify exact user-facing prompt and buttons + Skip behavior
        dlg_skip = FfmpegPromptDialog(manager)
        qtbot.addWidget(dlg_skip)
        assert dlg_skip.message_label.text() == (
            "FFmpeg is recommended for merging high-quality video and converting audio."
        )
        assert dlg_skip.download_btn.text() == "Download FFmpeg"
        assert dlg_skip.skip_btn.text() == "Skip for now"
        qtbot.mouseClick(dlg_skip.skip_btn, Qt.MouseButton.LeftButton)
        assert dlg_skip.result() == FfmpegPromptDialog.DialogCode.Rejected

        # 2. Verify Download click invokes manager.install_ffmpeg and closes on finish
        called = {"count": 0}

        def _fake_install() -> bool:
            called["count"] += 1
            manager.signals.ffmpeg_install_progress.emit(60, "Downloading FFmpeg...")
            manager.signals.ffmpeg_install_finished.emit(str(get_managed_bin_dir() / "ffmpeg"))
            return True

        monkeypatch.setattr(manager, "install_ffmpeg", _fake_install)

        dlg_dl = FfmpegPromptDialog(manager)
        qtbot.addWidget(dlg_dl)
        qtbot.mouseClick(dlg_dl.download_btn, Qt.MouseButton.LeftButton)
        assert called["count"] == 1
        assert dlg_dl.progress_bar.value() == 100
        assert dlg_dl.result() == FfmpegPromptDialog.DialogCode.Accepted
    finally:
        manager.shutdown()


def test_banner_settings_and_diagnostics_show_one_click_ffmpeg_download(
    qtbot,
    settings_manager,
    history_repo,
    isolated_app_dirs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_manager.save(AppSettings(download_folder=str(isolated_app_dirs / "downloads")))
    missing_ff = _MissingFfmpegService()
    manager = DownloadManager(
        settings_manager=settings_manager,
        history_repo=history_repo,
        ffmpeg_service=missing_ff,
        dependency_service=DependencyService(missing_ff),
    )
    manager.startup()

    try:
        window = MainWindow(manager)
        qtbot.addWidget(window)
        window.show()

        # Banner shows Download FFmpeg when FFmpeg is missing
        assert window.dep_banner.isVisible() is True
        assert window.dep_banner.download_ffmpeg_btn.isVisible() is True

        # Settings shows Download FFmpeg and hides CLI instructions
        window.navigate_to(MainWindow.PAGE_SETTINGS)
        settings_page: SettingsPage = window.settings_page
        assert settings_page.download_ffmpeg_btn.isVisible() is True

        # Diagnostic dialog shows one-click Download FFmpeg card and clean summary
        deps = manager.check_dependencies()
        diag = DiagnosticDialog(deps, manager.migration_report, window, manager=manager)
        qtbot.addWidget(diag)
        diag.show()
        assert diag.ffmpeg_card.isVisible() is True
        assert diag.download_ffmpeg_btn.text() == "Download FFmpeg"
        summary_text = diag.text_area.toPlainText().lower()
        assert "pip " not in summary_text
        assert "apt " not in summary_text

        # Simulate FFmpeg becoming installed and emitting signals
        ready_ff = _ReadyFfmpegService()
        monkeypatch.setattr(manager, "_ffmpeg", ready_ff)
        monkeypatch.setattr(manager, "_dependency_service", DependencyService(ready_ff))
        manager.signals.ffmpeg_install_finished.emit("/managed/bin/ffmpeg")
        manager.signals.dependencies_changed.emit()

        assert window.dep_banner.isVisible() is False
        assert settings_page.download_ffmpeg_btn.isVisible() is False
        assert diag.ffmpeg_card.isVisible() is False
        diag.close()
    finally:
        manager.shutdown()


def test_banner_signal_emits_on_click(qtbot) -> None:
    banner = DependencyBanner()
    qtbot.addWidget(banner)
    banner.show()

    statuses = DependencyService(_MissingFfmpegService()).check_all()
    missing = DependencyService.missing_recommended_summary(statuses)
    banner.update_statuses(missing)

    with qtbot.waitSignal(banner.download_ffmpeg_requested, timeout=1000):
        qtbot.mouseClick(banner.download_ffmpeg_btn, Qt.MouseButton.LeftButton)


def test_main_window_startup_prompt_and_manager_worker_flow(
    qtbot,
    settings_manager,
    history_repo,
    isolated_app_dirs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_manager.save(AppSettings(download_folder=str(isolated_app_dirs / "downloads")))

    # When FFmpeg is already available, prompt_ffmpeg_if_missing does nothing
    ready_manager = DownloadManager(
        settings_manager=settings_manager,
        history_repo=history_repo,
        ffmpeg_service=_ReadyFfmpegService(),
        dependency_service=DependencyService(_ReadyFfmpegService()),
    )
    ready_manager.startup()
    try:
        win_ready = MainWindow(ready_manager)
        qtbot.addWidget(win_ready)
        assert win_ready.prompt_ffmpeg_if_missing() is False
    finally:
        ready_manager.shutdown()

    # Background worker flow through DownloadManager.install_ffmpeg()
    ff_svc = FfmpegService()

    archive_bytes = _build_zip_bytes(
        {
            "ffmpeg": _make_mock_binary("ffmpeg"),
            "ffprobe": _make_mock_binary("ffprobe"),
        }
    )
    monkeypatch.setattr(
        "link_downloader.services.ffmpeg_service.get_ffmpeg_download_targets",
        lambda *_a, **_kw: [("zip", "https://example.test/ffmpeg.zip")],
    )
    orig_client = httpx.Client

    def _patched_client(*_a, **_kw):
        return orig_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=archive_bytes,
                    headers={"content-length": str(len(archive_bytes))},
                    request=request,
                )
            )
        )

    monkeypatch.setattr("link_downloader.services.ffmpeg_service.httpx.Client", _patched_client)

    manager = DownloadManager(
        settings_manager=settings_manager,
        history_repo=history_repo,
        ffmpeg_service=ff_svc,
        dependency_service=DependencyService(ff_svc),
    )
    manager.startup()
    try:
        with qtbot.waitSignal(manager.signals.ffmpeg_install_finished, timeout=5000) as sig:
            assert manager.install_ffmpeg() is True
        installed_path = Path(sig.args[0])
        assert installed_path.parent == get_managed_bin_dir().resolve()
        assert manager.is_ffmpeg_available() is True
    finally:
        manager.shutdown()
