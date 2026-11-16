"""GUI integration tests for MainWindow and all four pages using pytest-qt."""

from __future__ import annotations

import gc
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yt_dlp
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from link_downloader.config.defaults import AppSettings
from link_downloader.config.settings import SettingsManager
from link_downloader.core.enums import DownloadStatus, OverwriteBehavior, ThemeMode
from link_downloader.core.models import HistoryEntry
from link_downloader.database.repository import HistoryRepository
from link_downloader.services.dependency_service import DependencyService
from link_downloader.services.download_manager import DownloadManager
from link_downloader.services.ffmpeg_service import FfmpegService
from link_downloader.ui.main_window import MainWindow
from tests.fixtures.sample_metadata import SAMPLE_YOUTUBE_INFO

_BINARY_DOC = b"%PDF-1.7\nGUI integration test document payload\n%%EOF\n" * 64


class _GuiHttpHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_HEAD(self) -> None:
        if self.path == "/manual.pdf":
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(_BINARY_DOC)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/manual.pdf":
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(_BINARY_DOC)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(_BINARY_DOC)
            return
        self.send_response(404)
        self.end_headers()


@pytest.fixture
def gui_http_url() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GuiHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()


class _FixedFfmpegService(FfmpegService):
    def find_ffmpeg(self) -> str | None:
        return "/usr/bin/ffmpeg"


@pytest.fixture
def app_window(
    qtbot,
    isolated_app_dirs: Path,
    settings_manager: SettingsManager,
    history_repo: HistoryRepository,
):
    dl_dir = isolated_app_dirs / "downloads"
    settings_manager.save(AppSettings(download_folder=str(dl_dir)))
    ffmpeg_svc = _FixedFfmpegService()
    dep_svc = DependencyService(ffmpeg_svc)

    manager = DownloadManager(
        settings_manager=settings_manager,
        history_repo=history_repo,
        ffmpeg_service=ffmpeg_svc,
        dependency_service=dep_svc,
        allow_private=True,
    )
    manager.startup()
    window = MainWindow(manager, allow_private=True)
    qtbot.addWidget(window)
    window.show()
    yield window, manager
    manager.shutdown()
    window.close()
    window.deleteLater()
    QApplication.processEvents()
    gc.collect()


def test_navigation_across_all_pages(qtbot, app_window) -> None:
    window, _manager = app_window

    assert window.stack.currentIndex() == MainWindow.PAGE_DOWNLOAD

    qtbot.mouseClick(window.nav_queue, Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == MainWindow.PAGE_QUEUE

    qtbot.mouseClick(window.nav_history, Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == MainWindow.PAGE_HISTORY

    qtbot.mouseClick(window.nav_settings, Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == MainWindow.PAGE_SETTINGS

    qtbot.mouseClick(window.nav_download, Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == MainWindow.PAGE_DOWNLOAD


def test_url_input_validation_clear_and_paste(qtbot, app_window) -> None:
    window, _manager = app_window
    url_card = window.download_page.url_card

    url_card.url_input.setText("ftp://example.com/file.bin")
    assert "http" in url_card.feedback_label.text().lower()

    url_card.url_input.setText("https://example.com/file.pdf")
    assert "valid http/https url" in url_card.feedback_label.text().lower()
    assert url_card.analyze_btn.isEnabled() is True

    qtbot.mouseClick(url_card.clear_btn, Qt.MouseButton.LeftButton)
    assert url_card.url_input.text() == ""

    clipboard = QApplication.clipboard()
    assert clipboard is not None
    clipboard.setText("https://vimeo.com/123456")
    qtbot.mouseClick(url_card.paste_btn, Qt.MouseButton.LeftButton)
    assert url_card.url_input.text() == "https://vimeo.com/123456"


def test_analyze_and_download_direct_http_updates_queue_and_history(
    qtbot,
    app_window,
    gui_http_url: str,
    isolated_app_dirs: Path,
) -> None:
    window, manager = app_window
    url_card = window.download_page.url_card
    preview = window.download_page.preview_card

    target_url = f"{gui_http_url}/manual.pdf"
    url_card.url_input.setText(target_url)

    with qtbot.waitSignal(manager.signals.metadata_resolved, timeout=5000):
        qtbot.mouseClick(url_card.analyze_btn, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: preview.isVisible(), timeout=3000)
    assert preview.title_label.text() == "manual.pdf"
    assert preview.direct_details_card.isVisible() is True
    assert preview.media_formats_box.isVisible() is False

    # Trigger download and wait for job completion (enqueue_download emits history_updated first for QUEUED)
    qtbot.mouseClick(preview.download_btn, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: bool(manager.list_jobs())
        and manager.list_jobs()[0].status is DownloadStatus.COMPLETED,
        timeout=5000,
    )

    saved_file = isolated_app_dirs / "downloads" / "manual.pdf"
    assert saved_file.exists()
    assert saved_file.read_bytes() == _BINARY_DOC

    # Check QueuePage shows the item and HistoryPage displays the completed record
    assert len(window.queue_page._cards) == 1
    qtbot.mouseClick(window.nav_history, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.history_page.empty_state.isVisible() is False, timeout=2000)
    assert len(manager.history_repo.list_entries()) == 1


def test_analyze_ytdlp_media_and_format_filters(
    qtbot,
    app_window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeYoutubeDL:
        def __init__(self, opts: dict[str, Any]) -> None:
            self.opts = opts

        def __enter__(self) -> FakeYoutubeDL:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
            return SAMPLE_YOUTUBE_INFO

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    window, manager = app_window
    monkeypatch.setattr(manager._metadata_service, "fetch_thumbnail_bytes", lambda _url: None)
    url_card = window.download_page.url_card
    preview = window.download_page.preview_card

    url_card.url_input.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    with qtbot.waitSignal(manager.signals.metadata_resolved, timeout=5000):
        qtbot.mouseClick(url_card.analyze_btn, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: preview.isVisible(), timeout=3000)
    assert preview.title_label.text() == "Sample Cross-Platform Demo Video"
    assert preview.media_formats_box.isVisible() is True
    assert preview.direct_details_card.isVisible() is False

    all_count = preview.format_list.count()
    assert all_count >= 5

    # Click "Audio Only" filter chip
    audio_btn = next(b for b in preview._filter_group.buttons() if "Audio Only" in b.text())
    qtbot.mouseClick(audio_btn, Qt.MouseButton.LeftButton)
    audio_count = preview.format_list.count()
    assert 1 <= audio_count < all_count

    # Switch back to All
    all_btn = next(b for b in preview._filter_group.buttons() if b.text() == "All")
    qtbot.mouseClick(all_btn, Qt.MouseButton.LeftButton)
    assert preview.format_list.count() == all_count

    # Collapse inspector via close button
    qtbot.mouseClick(preview.close_btn, Qt.MouseButton.LeftButton)
    assert preview.isVisible() is False


def test_quick_download_direct_http_without_manual_format_pick(
    qtbot,
    app_window,
    gui_http_url: str,
    isolated_app_dirs: Path,
) -> None:
    window, manager = app_window
    url_card = window.download_page.url_card

    url_card.url_input.setText(f"{gui_http_url}/manual.pdf")
    qtbot.mouseClick(url_card.quick_download_btn, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: bool(manager.list_jobs())
        and manager.list_jobs()[0].status is DownloadStatus.COMPLETED,
        timeout=5000,
    )
    assert (isolated_app_dirs / "downloads" / "manual.pdf").exists()


def test_responsive_sidebar_and_preview_stacking(
    qtbot,
    app_window,
) -> None:
    window, _manager = app_window

    # Wide desktop width uses full sidebar
    window.resize(1040, 720)
    QApplication.processEvents()
    qtbot.waitUntil(lambda: window.sidebar.width() == 212, timeout=2000)

    # Compact width collapses sidebar to icon rail cleanly
    window.resize(660, 520)
    QApplication.processEvents()
    qtbot.waitUntil(lambda: window.sidebar.width() == 68, timeout=2000)

    # Expanding restores full sidebar labels
    window.resize(980, 700)
    QApplication.processEvents()
    qtbot.waitUntil(lambda: window.sidebar.width() == 212, timeout=2000)


def test_queue_page_concurrency_and_history_search_clear(
    qtbot,
    app_window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, manager = app_window

    # Pre-seed history entries directly in SQLite
    manager.history_repo.upsert_entry(
        HistoryEntry(
            id="h1",
            url="https://youtube.com/watch?v=1",
            platform="Youtube",
            title="Alpha Clip",
            filename="alpha.mp4",
            status=DownloadStatus.COMPLETED.value,
        )
    )
    manager.history_repo.upsert_entry(
        HistoryEntry(
            id="h2",
            url="https://vimeo.com/222",
            platform="Vimeo",
            title="Beta Documentary",
            filename="beta.mp4",
            status=DownloadStatus.FAILED.value,
            error_details="Network error",
        )
    )

    qtbot.mouseClick(window.nav_queue, Qt.MouseButton.LeftButton)
    window.queue_page.concurrency_spin.setValue(4)
    assert manager.settings.concurrent_downloads == 4

    qtbot.mouseClick(window.nav_history, Qt.MouseButton.LeftButton)
    window.history_page.refresh()
    assert window.history_page.empty_state.isVisible() is False

    window.history_page.search_input.setText("NonexistentTitleXYZ")
    assert window.history_page.empty_state.isVisible() is True

    window.history_page.search_input.setText("")
    assert window.history_page.empty_state.isVisible() is False

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    qtbot.mouseClick(window.history_page.clear_btn, Qt.MouseButton.LeftButton)
    assert len(manager.history_repo.list_entries()) == 0
    assert window.history_page.empty_state.isVisible() is True


def test_settings_persistence_and_theme_toggle(
    qtbot,
    app_window,
    isolated_app_dirs: Path,
) -> None:
    window, manager = app_window
    settings_page = window.settings_page

    qtbot.mouseClick(window.nav_settings, Qt.MouseButton.LeftButton)
    custom_dir = isolated_app_dirs / "custom_downloads"
    settings_page.folder_edit.setText(str(custom_dir))
    light_idx = settings_page.theme_combo.findData(ThemeMode.LIGHT.value)
    assert light_idx >= 0
    settings_page.theme_combo.setCurrentIndex(light_idx)

    overwrite_idx = settings_page.overwrite_combo.findData(OverwriteBehavior.OVERWRITE.value)
    settings_page.overwrite_combo.setCurrentIndex(overwrite_idx)

    with qtbot.waitSignal(manager.signals.settings_changed, timeout=2000):
        qtbot.mouseClick(settings_page.save_btn, Qt.MouseButton.LeftButton)

    assert manager.settings.theme == ThemeMode.LIGHT.value
    assert manager.settings.overwrite_behavior == OverwriteBehavior.OVERWRITE.value
    assert Path(manager.settings.download_folder) == custom_dir
    assert custom_dir.is_dir()
    assert settings_page.saved_badge.isVisible() is True


def test_history_pagination_and_narrow_responsive_pages(
    qtbot,
    app_window,
) -> None:
    window, manager = app_window

    # Seed 12 history items (default page size = 10 -> 2 pages)
    for idx in range(12):
        manager.history_repo.upsert_entry(
            HistoryEntry(
                id=f"pag-{idx:02d}",
                url=f"https://example.com/video/{idx}",
                platform="YouTube",
                title=f"Sample Clip {idx:02d}",
                filename=f"clip_{idx:02d}.mp4",
                status=DownloadStatus.COMPLETED.value,
            )
        )

    qtbot.mouseClick(window.nav_history, Qt.MouseButton.LeftButton)
    window.history_page.refresh()

    pbar = window.history_page.pagination_bar
    assert pbar.isVisible() is True
    assert pbar.total_pages == 2
    assert pbar.current_page == 1
    assert pbar.info_label.text() == "Showing 1-10 of 12"

    # Navigate to page 2
    qtbot.mouseClick(pbar.next_btn, Qt.MouseButton.LeftButton)
    assert pbar.current_page == 2
    assert pbar.info_label.text() == "Showing 11-12 of 12"

    # Navigate back to page 1
    qtbot.mouseClick(pbar.prev_btn, Qt.MouseButton.LeftButton)
    assert pbar.current_page == 1

    # Switch page size to 5 -> 3 pages
    idx_5 = pbar.page_size_combo.findData(5)
    assert idx_5 >= 0
    pbar.page_size_combo.setCurrentIndex(idx_5)
    assert pbar.total_pages == 3
    assert pbar.info_label.text() == "Showing 1-5 of 12"

    # Exercise narrow viewport (640x480) across all pages cleanly
    window.resize(640, 480)
    QApplication.processEvents()
    for nav_btn in (window.nav_download, window.nav_queue, window.nav_history, window.nav_settings):
        qtbot.mouseClick(nav_btn, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
    assert window.sidebar.width() == 68
