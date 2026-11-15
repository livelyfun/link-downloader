"""Main application window with sidebar navigation, banner, stacked pages, and clean shutdown."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from link_downloader import __app_name__, __version__
from link_downloader.platform.paths import get_app_icon_path
from link_downloader.services.dependency_service import DependencyService
from link_downloader.services.download_manager import DownloadManager
from link_downloader.ui.components.dependency_banner import DependencyBanner
from link_downloader.ui.dialogs.ffmpeg_prompt_dialog import FfmpegPromptDialog
from link_downloader.ui.pages.download_page import DownloadPage
from link_downloader.ui.pages.history_page import HistoryPage
from link_downloader.ui.pages.queue_page import QueuePage
from link_downloader.ui.pages.settings_page import SettingsPage
from link_downloader.ui.styles.theme import build_stylesheet, get_theme_palette, make_icon


class MainWindow(QMainWindow):
    """Primary Link Downloader desktop window."""

    PAGE_DOWNLOAD = 0
    PAGE_QUEUE = 1
    PAGE_HISTORY = 2
    PAGE_SETTINGS = 3

    def __init__(
        self,
        manager: DownloadManager,
        *,
        allow_private: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self.setWindowTitle(__app_name__)
        self.setMinimumSize(900, 620)
        self.resize(1140, 780)

        icon_path = get_app_icon_path()
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(216)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(14, 18, 14, 16)
        side_layout.setSpacing(6)

        # Brand Header
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        logo_lbl = QLabel("LD")
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_lbl.setFixedSize(34, 34)
        logo_lbl.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #4f46e5, stop:1 #8b5cf6);"
            "color: #ffffff; font-weight: 800; font-size: 14px; border-radius: 9px;"
        )
        brand_row.addWidget(logo_lbl)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand_name = QLabel(__app_name__)
        brand_name.setStyleSheet("font-size: 14px; font-weight: 700;")
        brand_ver = QLabel(f"v{__version__}")
        brand_ver.setObjectName("MutedLabel")
        brand_col.addWidget(brand_name)
        brand_col.addWidget(brand_ver)
        brand_row.addLayout(brand_col)
        brand_row.addStretch()
        side_layout.addLayout(brand_row)
        side_layout.addSpacing(14)

        nav_lbl = QLabel("NAVIGATION")
        nav_lbl.setObjectName("SectionTitle")
        side_layout.addWidget(nav_lbl)
        side_layout.addSpacing(2)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        self.nav_download = self._make_nav_btn("Download", "download", self.PAGE_DOWNLOAD)
        self.nav_queue = self._make_nav_btn("Queue", "queue", self.PAGE_QUEUE)
        self.nav_history = self._make_nav_btn("History", "history", self.PAGE_HISTORY)
        self.nav_settings = self._make_nav_btn("Settings", "settings", self.PAGE_SETTINGS)

        for btn in (self.nav_download, self.nav_queue, self.nav_history, self.nav_settings):
            self._nav_group.addButton(btn)
            side_layout.addWidget(btn)

        self.nav_download.setChecked(True)
        side_layout.addStretch()

        self.active_status_label = QLabel("Idle")
        self.active_status_label.setObjectName("MutedLabel")
        side_layout.addWidget(self.active_status_label)

        root.addWidget(self.sidebar)

        # Main workspace area
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.dep_banner = DependencyBanner()
        self.dep_banner.inspect_requested.connect(lambda: self.navigate_to(self.PAGE_SETTINGS))
        self.dep_banner.download_ffmpeg_requested.connect(self._on_banner_download_ffmpeg)
        banner_wrap = QWidget()
        banner_lay = QVBoxLayout(banner_wrap)
        banner_lay.setContentsMargins(24, 14, 24, 0)
        banner_lay.addWidget(self.dep_banner)
        self._banner_wrap = banner_wrap
        right_layout.addWidget(banner_wrap)

        self.stack = QStackedWidget()
        self.download_page = DownloadPage(manager, allow_private=allow_private)
        self.queue_page = QueuePage(manager)
        self.history_page = HistoryPage(manager)
        self.settings_page = SettingsPage(manager)

        self.stack.addWidget(self.download_page)
        self.stack.addWidget(self.queue_page)
        self.stack.addWidget(self.history_page)
        self.stack.addWidget(self.settings_page)
        right_layout.addWidget(self.stack, 1)

        root.addWidget(right_col, 1)

        # Signals
        self.download_page.open_queue_requested.connect(lambda: self.navigate_to(self.PAGE_QUEUE))
        self.history_page.redownload_requested.connect(self._on_redownload)
        self.settings_page.theme_changed.connect(self.apply_theme)
        self._manager.signals.queue_changed.connect(self._update_queue_badges)
        self._manager.signals.job_updated.connect(lambda _j: self._update_queue_badges())
        self._manager.signals.dependencies_changed.connect(self._refresh_dependency_banner)
        self._manager.signals.ffmpeg_install_progress.connect(self._on_ffmpeg_banner_progress)
        self._manager.signals.ffmpeg_install_finished.connect(lambda _p: self._refresh_dependency_banner())
        self._manager.signals.ffmpeg_install_failed.connect(self._on_ffmpeg_banner_failed)

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self.navigate_to(self.PAGE_DOWNLOAD))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self.navigate_to(self.PAGE_QUEUE))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self.navigate_to(self.PAGE_HISTORY))
        QShortcut(QKeySequence("Ctrl+4"), self, lambda: self.navigate_to(self.PAGE_SETTINGS))
        QShortcut(QKeySequence("Ctrl+L"), self, self._focus_url_input)

        self.apply_theme(self._manager.settings.theme)
        self._refresh_dependency_banner()
        self._update_queue_badges()

    def _make_nav_btn(self, label: str, icon_name: str, page_index: int) -> QPushButton:
        btn = QPushButton(f"  {label}")
        btn.setObjectName("NavButton")
        btn.setCheckable(True)
        btn.setProperty("icon_name", icon_name)
        btn.setIcon(make_icon(icon_name, "#cbd5e1", 18))
        btn.clicked.connect(lambda: self.navigate_to(page_index))
        return btn

    def navigate_to(self, page_index: int) -> None:
        self.stack.setCurrentIndex(page_index)
        buttons = [self.nav_download, self.nav_queue, self.nav_history, self.nav_settings]
        if 0 <= page_index < len(buttons):
            buttons[page_index].setChecked(True)
        if page_index == self.PAGE_HISTORY:
            self.history_page.refresh()
        elif page_index == self.PAGE_SETTINGS:
            self.settings_page.refresh_dependencies()

    def _focus_url_input(self) -> None:
        self.navigate_to(self.PAGE_DOWNLOAD)
        self.download_page.url_card.url_input.setFocus()

    def _on_redownload(self, url: str) -> None:
        self.navigate_to(self.PAGE_DOWNLOAD)
        self.download_page.analyze_external_url(url)

    def _refresh_dependency_banner(self) -> None:
        statuses = self._manager.check_dependencies()
        missing = DependencyService.missing_recommended_summary(statuses)
        self.dep_banner.set_installing(self._manager.is_installing_ffmpeg())
        self.dep_banner.update_statuses(missing)
        self._banner_wrap.setVisible(not self.dep_banner.isHidden())

    def _on_banner_download_ffmpeg(self) -> None:
        self.dep_banner.set_installing(True, 0, "Downloading FFmpeg...")
        self._banner_wrap.setVisible(not self.dep_banner.isHidden())
        self._manager.install_ffmpeg()

    def _on_ffmpeg_banner_progress(self, percent: int, message: str) -> None:
        self.dep_banner.set_installing(True, percent, message)
        self._banner_wrap.setVisible(not self.dep_banner.isHidden())

    def _on_ffmpeg_banner_failed(self, error_msg: str) -> None:
        self.dep_banner.set_error(error_msg)
        self._banner_wrap.setVisible(not self.dep_banner.isHidden())

    def prompt_ffmpeg_if_missing(self) -> bool:
        """Show the optional FFmpeg setup dialog if FFmpeg is not installed yet."""
        if self._manager.is_ffmpeg_available():
            return False
        dlg = FfmpegPromptDialog(self._manager, self)
        return dlg.exec() == FfmpegPromptDialog.DialogCode.Accepted

    def _update_queue_badges(self) -> None:
        jobs = self._manager.list_jobs()
        active = sum(1 for j in jobs if j.status.is_active)
        waiting = sum(1 for j in jobs if j.status.value in ("queued", "waiting", "paused"))
        pending = active + waiting
        self.nav_queue.setText(f"  Queue ({pending})" if pending > 0 else "  Queue")
        if active > 0:
            self.active_status_label.setText(f"{active} downloading · {waiting} waiting")
        elif waiting > 0:
            self.active_status_label.setText(f"{waiting} queued / paused")
        else:
            self.active_status_label.setText("Ready · Local Mode")

    def apply_theme(self, theme_mode: str) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(theme_mode))
        palette = get_theme_palette(theme_mode)
        for btn in (self.nav_download, self.nav_queue, self.nav_history, self.nav_settings):
            icon_name = str(btn.property("icon_name") or "link")
            btn.setIcon(make_icon(icon_name, palette["icon"], 18))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._manager.shutdown()
        super().closeEvent(event)
