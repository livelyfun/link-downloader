"""Native-style desktop Settings page with structured preference rows and component diagnostics."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from link_downloader.config.defaults import (
    DEFAULT_FORMAT_PRESETS,
    DEFAULT_QUALITY_OPTIONS,
    MAX_CONCURRENT_DOWNLOADS,
    MIN_CONCURRENT_DOWNLOADS,
    AppSettings,
)
from link_downloader.core.enums import DependencyCategory, OverwriteBehavior, ThemeMode
from link_downloader.core.models import DependencyStatus
from link_downloader.platform.file_actions import open_folder
from link_downloader.services.download_manager import DownloadManager
from link_downloader.ui.dialogs.diagnostic_dialog import DiagnosticDialog
from link_downloader.ui.styles.theme import make_icon


class _ResponsiveSettingRow(QFrame):
    """Preference row that switches cleanly between horizontal and stacked layouts."""

    def __init__(
        self,
        title_text: str,
        subtitle_text: str,
        control: QWidget,
        *,
        is_last: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if not is_last:
            self.setObjectName("SettingRow")
        self._box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box.setContentsMargins(0, 10, 0, 10)
        self._box.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-weight: 600;")
        sub_lbl = QLabel(subtitle_text)
        sub_lbl.setObjectName("MutedLabel")
        sub_lbl.setWordWrap(True)
        sub_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text_col.addWidget(title_lbl)
        text_col.addWidget(sub_lbl)

        self._box.addLayout(text_col, 1)
        self._box.addWidget(control)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        direction = (
            QBoxLayout.Direction.TopToBottom
            if event.size().width() < 520
            else QBoxLayout.Direction.LeftToRight
        )
        if self._box.direction() != direction:
            self._box.setDirection(direction)


class SettingsPage(QWidget):
    """Structured desktop settings groups and component health diagnostics."""

    theme_changed = Signal(str)

    def __init__(self, manager: DownloadManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Sticky top toolbar with Save / Discard
        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(20, 10, 20, 10)
        tb_lay.setSpacing(8)

        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        tb_lay.addWidget(title)

        self.saved_badge = QLabel("Saved")
        self.saved_badge.setObjectName("BadgeSuccess")
        self.saved_badge.setVisible(False)
        tb_lay.addWidget(self.saved_badge)
        tb_lay.addStretch()

        self.reset_btn = QPushButton("Discard")
        self.reset_btn.setObjectName("GhostButton")
        self.reset_btn.clicked.connect(self.load_from_manager)
        tb_lay.addWidget(self.reset_btn)

        self.save_btn = QPushButton("Save Changes")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.setIcon(make_icon("check", "#ffffff", 14))
        self.save_btn.clicked.connect(self._save_settings)
        tb_lay.addWidget(self.save_btn)
        outer.addWidget(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("ScrollContent")
        scroll.setWidget(content)

        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(20, 16, 20, 24)
        self._layout.setSpacing(14)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Section 1: Storage & Files
        storage_card, s_lay = self._make_section("STORAGE & FILES")

        dest_wrap = QWidget()
        dest_row = QHBoxLayout(dest_wrap)
        dest_row.setContentsMargins(0, 0, 0, 0)
        dest_row.setSpacing(6)
        self.folder_edit = QLineEdit()
        self.folder_edit.setMinimumWidth(110)
        dest_row.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("GhostButton")
        browse_btn.clicked.connect(self._browse_folder)
        dest_row.addWidget(browse_btn)

        open_btn = QPushButton()
        open_btn.setObjectName("GhostButton")
        open_btn.setIcon(make_icon("folder", "#475569", 14))
        open_btn.setToolTip("Open downloads folder")
        open_btn.clicked.connect(lambda: open_folder(self.folder_edit.text().strip()))
        dest_row.addWidget(open_btn)
        s_lay.addWidget(
            self._make_row(
                "Download Folder",
                "Destination directory where downloaded files are saved.",
                dest_wrap,
            )
        )

        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItem("Rename automatically (safe)", OverwriteBehavior.RENAME.value)
        self.overwrite_combo.addItem("Overwrite existing file", OverwriteBehavior.OVERWRITE.value)
        self.overwrite_combo.addItem("Skip if file exists", OverwriteBehavior.SKIP.value)
        s_lay.addWidget(
            self._make_row(
                "Duplicate File Handling",
                "Action to take when a file with the same name already exists.",
                self.overwrite_combo,
            )
        )

        self.sanitize_check = QCheckBox("Sanitize unsafe characters in filenames")
        s_lay.addWidget(
            self._make_row(
                "Safe Filenames",
                "Automatically clean special OS characters and prevent path issues.",
                self.sanitize_check,
                is_last=True,
            )
        )
        self._layout.addWidget(storage_card)

        # Section 2: Media, Queue & Network
        media_card, m_lay = self._make_section("DOWNLOADS, MEDIA & NETWORK")

        self.format_combo = QComboBox()
        for label, value in DEFAULT_FORMAT_PRESETS:
            self.format_combo.addItem(label, value)
        m_lay.addWidget(
            self._make_row(
                "Default Format Preset",
                "Preferred container and stream rule for video/audio links.",
                self.format_combo,
            )
        )

        self.quality_combo = QComboBox()
        for q in DEFAULT_QUALITY_OPTIONS:
            self.quality_combo.addItem(q.upper() if q != "best" else "Best Available", q)
        m_lay.addWidget(
            self._make_row(
                "Default Resolution",
                "Target resolution cap when downloading video platforms.",
                self.quality_combo,
            )
        )

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(MIN_CONCURRENT_DOWNLOADS, MAX_CONCURRENT_DOWNLOADS)
        m_lay.addWidget(
            self._make_row(
                "Parallel Transfers",
                "Maximum number of downloads running simultaneously (1-5).",
                self.concurrency_spin,
            )
        )

        self.mp3_check = QCheckBox("Convert audio-only downloads to MP3")
        m_lay.addWidget(
            self._make_row(
                "MP3 Audio Conversion",
                "Automatically transcode extracted audio tracks (uses FFmpeg).",
                self.mp3_check,
            )
        )

        self.ipv4_check = QCheckBox("Prefer IPv4 connections")
        m_lay.addWidget(
            self._make_row(
                "Network Protocol",
                "Avoid stalls on networks with incomplete IPv6 routing.",
                self.ipv4_check,
                is_last=True,
            )
        )
        self._layout.addWidget(media_card)

        # Section 3: Appearance
        theme_card, t_lay = self._make_section("APPEARANCE")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Porcelain Light (Default)", ThemeMode.LIGHT.value)
        self.theme_combo.addItem("Soft Pearl", ThemeMode.DARK.value)
        t_lay.addWidget(
            self._make_row(
                "Color Theme",
                "Choose between Porcelain Light and Soft Pearl neumorphic palettes.",
                self.theme_combo,
                is_last=True,
            )
        )
        self._layout.addWidget(theme_card)

        # Section 4: Components & Diagnostics
        deps_card = QFrame()
        deps_card.setObjectName("Card")
        d_lay = QVBoxLayout(deps_card)
        d_lay.setContentsMargins(16, 14, 16, 14)
        d_lay.setSpacing(10)

        self._deps_top_box = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._deps_top_box.setSpacing(8)
        d_hdr_col = QVBoxLayout()
        d_hdr_col.setSpacing(2)
        d_title = QLabel("COMPONENTS & DIAGNOSTICS")
        d_title.setObjectName("SectionTitle")
        deps_desc = QLabel(
            "Verify built-in components and install FFmpeg in one click for 4K merging and MP3 conversion."
        )
        deps_desc.setObjectName("MutedLabel")
        deps_desc.setWordWrap(True)
        deps_desc.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        d_hdr_col.addWidget(d_title)
        d_hdr_col.addWidget(deps_desc)
        self._deps_top_box.addLayout(d_hdr_col, 1)

        d_btns = QHBoxLayout()
        d_btns.setSpacing(6)
        self.download_ffmpeg_btn = QPushButton("Download FFmpeg")
        self.download_ffmpeg_btn.setObjectName("PrimaryButton")
        self.download_ffmpeg_btn.setIcon(make_icon("download", "#ffffff", 14))
        self.download_ffmpeg_btn.clicked.connect(self._on_download_ffmpeg_clicked)
        self.download_ffmpeg_btn.setVisible(False)
        d_btns.addWidget(self.download_ffmpeg_btn)

        self.recheck_btn = QPushButton("Re-check")
        self.recheck_btn.setObjectName("GhostButton")
        self.recheck_btn.setIcon(make_icon("retry", "#475569", 14))
        self.recheck_btn.clicked.connect(self.refresh_dependencies)
        d_btns.addWidget(self.recheck_btn)

        self.diag_btn = QPushButton("Diagnostics...")
        self.diag_btn.setObjectName("GhostButton")
        self.diag_btn.clicked.connect(self._open_diagnostics)
        d_btns.addWidget(self.diag_btn)
        d_btns.addStretch(0)
        self._deps_top_box.addLayout(d_btns)
        d_lay.addLayout(self._deps_top_box)

        self.ffmpeg_progress_bar = QProgressBar()
        self.ffmpeg_progress_bar.setRange(0, 100)
        self.ffmpeg_progress_bar.setValue(0)
        self.ffmpeg_progress_bar.setVisible(False)
        d_lay.addWidget(self.ffmpeg_progress_bar)

        self.ffmpeg_status_label = QLabel("")
        self.ffmpeg_status_label.setObjectName("MutedLabel")
        self.ffmpeg_status_label.setWordWrap(True)
        self.ffmpeg_status_label.setVisible(False)
        d_lay.addWidget(self.ffmpeg_status_label)

        self.deps_list_layout = QVBoxLayout()
        self.deps_list_layout.setSpacing(6)
        d_lay.addLayout(self.deps_list_layout)
        self._layout.addWidget(deps_card)

        self._last_deps: list[DependencyStatus] = []
        self._manager.signals.ffmpeg_install_started.connect(self._on_ffmpeg_started)
        self._manager.signals.ffmpeg_install_progress.connect(self._on_ffmpeg_progress)
        self._manager.signals.ffmpeg_install_finished.connect(self._on_ffmpeg_finished)
        self._manager.signals.ffmpeg_install_failed.connect(self._on_ffmpeg_failed)
        self._manager.signals.dependencies_changed.connect(self.refresh_dependencies)

        self.load_from_manager()
        self.refresh_dependencies()

    def _make_section(self, title_text: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 6)
        lay.setSpacing(0)
        lbl = QLabel(title_text)
        lbl.setObjectName("SectionTitle")
        lay.addWidget(lbl)
        lay.addSpacing(6)
        return card, lay

    @staticmethod
    def _make_row(
        title_text: str,
        subtitle_text: str,
        control: QWidget,
        *,
        is_last: bool = False,
    ) -> QFrame:
        return _ResponsiveSettingRow(
            title_text,
            subtitle_text,
            control,
            is_last=is_last,
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        direction = (
            QBoxLayout.Direction.TopToBottom
            if event.size().width() < 560
            else QBoxLayout.Direction.LeftToRight
        )
        if self._deps_top_box.direction() != direction:
            self._deps_top_box.setDirection(direction)

    def _browse_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Choose Download Folder",
            self.folder_edit.text().strip(),
        )
        if chosen:
            self.folder_edit.setText(chosen)

    def load_from_manager(self) -> None:
        s = self._manager.settings
        self.folder_edit.setText(s.download_folder)
        self._set_combo_by_data(self.overwrite_combo, s.overwrite_behavior)
        self.sanitize_check.setChecked(s.auto_sanitize_filenames)
        self._set_combo_by_data(self.format_combo, s.default_format)
        self._set_combo_by_data(self.quality_combo, s.default_quality)
        self.concurrency_spin.setValue(s.concurrent_downloads)
        self.mp3_check.setChecked(s.auto_convert_mp3)
        self.ipv4_check.setChecked(s.prefer_ipv4)
        self._set_combo_by_data(self.theme_combo, s.theme)
        self.saved_badge.setVisible(False)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _save_settings(self) -> None:
        prev = self._manager.settings
        updated = AppSettings(
            download_folder=self.folder_edit.text().strip() or prev.download_folder,
            default_format=str(self.format_combo.currentData()),
            default_quality=str(self.quality_combo.currentData()),
            auto_convert_mp3=self.mp3_check.isChecked(),
            concurrent_downloads=self.concurrency_spin.value(),
            overwrite_behavior=str(self.overwrite_combo.currentData()),
            auto_sanitize_filenames=self.sanitize_check.isChecked(),
            prefer_ipv4=self.ipv4_check.isChecked(),
            theme=str(self.theme_combo.currentData()),
            legacy_migrated=prev.legacy_migrated,
        )
        saved = self._manager.update_settings(updated)
        self.saved_badge.setVisible(True)
        self.theme_changed.emit(saved.theme)

    def refresh_dependencies(self) -> None:
        while self.deps_list_layout.count():
            item = self.deps_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._last_deps = self._manager.check_dependencies()
        ffmpeg_missing = any(d.name == "FFmpeg" and not d.available for d in self._last_deps)
        installing = self._manager.is_installing_ffmpeg()
        self.download_ffmpeg_btn.setVisible(ffmpeg_missing or installing)
        self.download_ffmpeg_btn.setEnabled(not installing)
        if not installing:
            self.download_ffmpeg_btn.setText("Download FFmpeg")

        for dep in self._last_deps:
            row = QFrame()
            row.setObjectName("SubCard")
            lay = QVBoxLayout(row)
            lay.setContentsMargins(12, 8, 12, 8)
            lay.setSpacing(3)

            top = QHBoxLayout()
            name_lbl = QLabel(dep.name)
            name_lbl.setStyleSheet("font-weight: 600;")
            top.addWidget(name_lbl, 1)

            if dep.available:
                badge_text = f"Available · {dep.version}" if dep.version else "Available"
                badge_obj = "BadgeSuccess"
            elif dep.category == DependencyCategory.OPTIONAL:
                badge_text = "Optional"
                badge_obj = "MutedLabel"
            else:
                badge_text = "Not Installed"
                badge_obj = "BadgeWarning"

            status_lbl = QLabel(badge_text)
            status_lbl.setObjectName(badge_obj)
            top.addWidget(status_lbl)

            if dep.name == "FFmpeg" and not dep.available:
                row_dl_btn = QPushButton("Download FFmpeg")
                row_dl_btn.setObjectName("PrimaryButton")
                row_dl_btn.setEnabled(not installing)
                row_dl_btn.clicked.connect(self._on_download_ffmpeg_clicked)
                top.addWidget(row_dl_btn)

            lay.addLayout(top)

            desc_lbl = QLabel(dep.impact)
            desc_lbl.setObjectName("MutedLabel")
            desc_lbl.setWordWrap(True)
            lay.addWidget(desc_lbl)

            if dep.available and dep.path:
                path_lbl = QLabel(f"Location: {dep.path}")
                path_lbl.setObjectName("MutedLabel")
                path_lbl.setWordWrap(True)
                lay.addWidget(path_lbl)
            elif not dep.available:
                hint_lbl = QLabel(dep.install_hint)
                hint_lbl.setObjectName("MutedLabel")
                hint_lbl.setWordWrap(True)
                lay.addWidget(hint_lbl)

            self.deps_list_layout.addWidget(row)

    def _on_download_ffmpeg_clicked(self) -> None:
        self._on_ffmpeg_started()
        self._manager.install_ffmpeg()

    def _on_ffmpeg_started(self) -> None:
        self.download_ffmpeg_btn.setVisible(True)
        self.download_ffmpeg_btn.setEnabled(False)
        self.download_ffmpeg_btn.setText("Downloading...")
        self.ffmpeg_progress_bar.setVisible(True)
        self.ffmpeg_progress_bar.setValue(0)
        self.ffmpeg_status_label.setObjectName("MutedLabel")
        self.ffmpeg_status_label.style().unpolish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.style().polish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.setText("Downloading FFmpeg...")
        self.ffmpeg_status_label.setVisible(True)

    def _on_ffmpeg_progress(self, percent: int, message: str) -> None:
        self.download_ffmpeg_btn.setEnabled(False)
        self.download_ffmpeg_btn.setText(f"Downloading... ({percent}%)")
        self.ffmpeg_progress_bar.setVisible(True)
        self.ffmpeg_progress_bar.setValue(percent)
        self.ffmpeg_status_label.setText(message)
        self.ffmpeg_status_label.setVisible(True)

    def _on_ffmpeg_finished(self, _path: str) -> None:
        self.ffmpeg_progress_bar.setValue(100)
        self.ffmpeg_status_label.setObjectName("SuccessLabel")
        self.ffmpeg_status_label.style().unpolish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.style().polish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.setText("FFmpeg is installed and ready.")
        self.ffmpeg_status_label.setVisible(True)
        self.refresh_dependencies()

    def _on_ffmpeg_failed(self, error_msg: str) -> None:
        self.download_ffmpeg_btn.setEnabled(True)
        self.download_ffmpeg_btn.setText("Download FFmpeg")
        self.ffmpeg_progress_bar.setVisible(False)
        self.ffmpeg_status_label.setObjectName("ErrorLabel")
        self.ffmpeg_status_label.style().unpolish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.style().polish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.setText(error_msg)
        self.ffmpeg_status_label.setVisible(True)
        self.refresh_dependencies()

    def _open_diagnostics(self) -> None:
        dlg = DiagnosticDialog(
            self._last_deps,
            self._manager.migration_report,
            self,
            manager=self._manager,
        )
        dlg.exec()
