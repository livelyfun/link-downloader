"""Main desktop application window with responsive neumorphic sidebar and workspaces."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QPixmap, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from link_downloader import __app_name__, __version__
from link_downloader.platform.file_actions import open_folder
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
    """Primary responsive Link Downloader desktop window."""

    PAGE_DOWNLOAD = 0
    PAGE_QUEUE = 1
    PAGE_HISTORY = 2
    PAGE_SETTINGS = 3
    COMPACT_SIDEBAR_BREAKPOINT = 760

    def __init__(
        self,
        manager: DownloadManager,
        *,
        allow_private: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._sidebar_compact = False
        self._pending_count = 0

        self.setWindowTitle(__app_name__)
        self.setMinimumSize(640, 480)
        self.resize(1080, 740)

        icon_path = get_app_icon_path()
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Responsive Neumorphic Sidebar
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(212)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(12, 16, 12, 14)
        side_layout.setSpacing(6)

        # Sculpted Brand Header
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)

        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_lbl.setFixedSize(36, 36)
        if icon_path is not None and not QPixmap(str(icon_path)).isNull():
            pix = QPixmap(str(icon_path)).scaled(
                34,
                34,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl.setPixmap(pix)
        else:
            logo_lbl.setPixmap(make_icon("brand_logo", "#2563eb", 22).pixmap(22, 22))
        brand_row.addWidget(logo_lbl)

        self._brand_col_widget = QWidget()
        brand_col = QVBoxLayout(self._brand_col_widget)
        brand_col.setContentsMargins(0, 0, 0, 0)
        brand_col.setSpacing(0)
        brand_name = QLabel(__app_name__)
        brand_name.setStyleSheet("font-size: 13px; font-weight: 700;")
        brand_ver = QLabel(f"v{__version__}")
        brand_ver.setObjectName("MutedLabel")
        brand_col.addWidget(brand_name)
        brand_col.addWidget(brand_ver)
        brand_row.addWidget(self._brand_col_widget, 1)
        side_layout.addLayout(brand_row)
        side_layout.addSpacing(12)

        self._nav_section_lbl = QLabel("WORKSPACE")
        self._nav_section_lbl.setObjectName("SectionTitle")
        side_layout.addWidget(self._nav_section_lbl)
        side_layout.addSpacing(2)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        self.nav_download = self._make_nav_btn("Downloads", "download", self.PAGE_DOWNLOAD, "Ctrl+1")
        self.nav_queue = self._make_nav_btn("Queue", "queue", self.PAGE_QUEUE, "Ctrl+2")
        self.nav_history = self._make_nav_btn("History", "history", self.PAGE_HISTORY, "Ctrl+3")
        self.nav_settings = self._make_nav_btn("Settings", "settings", self.PAGE_SETTINGS, "Ctrl+4")

        for btn in (self.nav_download, self.nav_queue, self.nav_history, self.nav_settings):
            self._nav_group.addButton(btn)
            side_layout.addWidget(btn)

        self.nav_download.setChecked(True)
        side_layout.addStretch()

        # Sidebar utility footer card
        self._status_box = QFrame()
        self._status_box.setObjectName("StatusBox")
        sb_lay = QVBoxLayout(self._status_box)
        sb_lay.setContentsMargins(10, 10, 10, 10)
        sb_lay.setSpacing(6)

        self.active_status_label = QLabel("Ready · Idle")
        self.active_status_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        sb_lay.addWidget(self.active_status_label)

        self.ffmpeg_sidebar_label = QLabel("FFmpeg: Checking...")
        self.ffmpeg_sidebar_label.setObjectName("MutedLabel")
        sb_lay.addWidget(self.ffmpeg_sidebar_label)

        self.sidebar_folder_btn = QPushButton("Open Downloads")
        self.sidebar_folder_btn.setObjectName("GhostButton")
        self.sidebar_folder_btn.setIcon(make_icon("folder", "#475569", 13))
        self.sidebar_folder_btn.clicked.connect(
            lambda: open_folder(self._manager.settings.download_folder)
        )
        sb_lay.addWidget(self.sidebar_folder_btn)

        side_layout.addWidget(self._status_box)
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
        banner_lay.setContentsMargins(18, 10, 18, 6)
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
        self._apply_responsive_sidebar(self.width())

    def _make_nav_btn(
        self, label: str, icon_name: str, page_index: int, shortcut: str
    ) -> QPushButton:
        btn = QPushButton(f"  {label}")
        btn.setObjectName("NavButton")
        btn.setCheckable(True)
        btn.setProperty("icon_name", icon_name)
        btn.setProperty("full_label", label)
        btn.setToolTip(f"{label} ({shortcut})")
        btn.setIcon(make_icon(icon_name, "#475569", 16))
        btn.clicked.connect(lambda: self.navigate_to(page_index))
        return btn

    def _apply_responsive_sidebar(self, win_width: int) -> None:
        compact = win_width < self.COMPACT_SIDEBAR_BREAKPOINT
        if compact == self._sidebar_compact and self.sidebar.width() in (68, 212):
            return
        self._sidebar_compact = compact
        self.sidebar.setFixedWidth(68 if compact else 212)
        self._brand_col_widget.setVisible(not compact)
        self._nav_section_lbl.setVisible(not compact)
        self._status_box.setVisible(not compact)
        self._refresh_nav_button_labels()

    def _refresh_nav_button_labels(self) -> None:
        for btn in (self.nav_download, self.nav_queue, self.nav_history, self.nav_settings):
            if self._sidebar_compact:
                btn.setText("")
            else:
                base = str(btn.property("full_label") or "")
                if btn is self.nav_queue and self._pending_count > 0:
                    btn.setText(f"  {base} ({self._pending_count})")
                else:
                    btn.setText(f"  {base}")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_sidebar(event.size().width())

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

        ffmpeg_ok = any(d.name == "FFmpeg" and d.available for d in statuses)
        if self._manager.is_installing_ffmpeg():
            self.ffmpeg_sidebar_label.setText("FFmpeg: Downloading...")
            self.ffmpeg_sidebar_label.setObjectName("MutedLabel")
        elif ffmpeg_ok:
            self.ffmpeg_sidebar_label.setText("FFmpeg: Ready")
            self.ffmpeg_sidebar_label.setObjectName("SuccessLabel")
        else:
            self.ffmpeg_sidebar_label.setText("FFmpeg: Not Installed")
            self.ffmpeg_sidebar_label.setObjectName("MutedLabel")
        self.ffmpeg_sidebar_label.style().unpolish(self.ffmpeg_sidebar_label)
        self.ffmpeg_sidebar_label.style().polish(self.ffmpeg_sidebar_label)

    def _on_banner_download_ffmpeg(self) -> None:
        self.dep_banner.set_installing(True, 0, "Downloading FFmpeg...")
        self._banner_wrap.setVisible(not self.dep_banner.isHidden())
        self._manager.install_ffmpeg()

    def _on_ffmpeg_banner_progress(self, percent: int, message: str) -> None:
        self.dep_banner.set_installing(True, percent, message)
        self._banner_wrap.setVisible(not self.dep_banner.isHidden())
        self.ffmpeg_sidebar_label.setText(f"FFmpeg: {percent}%")

    def _on_ffmpeg_banner_failed(self, error_msg: str) -> None:
        self.dep_banner.set_error(error_msg)
        self._banner_wrap.setVisible(not self.dep_banner.isHidden())
        self.ffmpeg_sidebar_label.setText("FFmpeg: Not Installed")

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
        self._pending_count = active + waiting
        self._refresh_nav_button_labels()
        if active > 0:
            self.active_status_label.setText(f"{active} active · {waiting} waiting")
        elif waiting > 0:
            self.active_status_label.setText(f"{waiting} queued / paused")
        else:
            self.active_status_label.setText("Ready · Idle")

    def apply_theme(self, theme_mode: str) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(theme_mode))
        palette = get_theme_palette(theme_mode)
        for btn in (self.nav_download, self.nav_queue, self.nav_history, self.nav_settings):
            icon_name = str(btn.property("icon_name") or "link")
            btn.setIcon(make_icon(icon_name, palette["icon"], 16))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._manager.shutdown()
        super().closeEvent(event)
