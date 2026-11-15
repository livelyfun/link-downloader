"""Settings page with storage, media, concurrency, theme, and dependency diagnostics."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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


class SettingsPage(QWidget):
    """Organized settings groups and live dependency diagnostics."""

    theme_changed = Signal(str)

    def __init__(self, manager: DownloadManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("ScrollContent")
        scroll.setWidget(content)

        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(24, 22, 24, 24)
        self._layout.setSpacing(16)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QHBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()

        self.saved_badge = QLabel("Settings saved")
        self.saved_badge.setObjectName("BadgeSuccess")
        self.saved_badge.setVisible(False)
        header.addWidget(self.saved_badge)
        self._layout.addLayout(header)

        # Card 1: Storage & Files
        storage_card = self._make_card("STORAGE & FILE HANDLING")
        s_lay = storage_card.layout()

        dest_lbl = QLabel("Download Destination Folder")
        dest_lbl.setStyleSheet("font-weight: 600;")
        s_lay.addWidget(dest_lbl)

        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)
        self.folder_edit = QLineEdit()
        dest_row.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("GhostButton")
        browse_btn.clicked.connect(self._browse_folder)
        dest_row.addWidget(browse_btn)

        open_btn = QPushButton("Open")
        open_btn.setObjectName("GhostButton")
        open_btn.setIcon(make_icon("folder", "#cbd5e1", 15))
        open_btn.clicked.connect(lambda: open_folder(self.folder_edit.text().strip()))
        dest_row.addWidget(open_btn)
        s_lay.addLayout(dest_row)

        collision_row = QHBoxLayout()
        collision_lbl = QLabel("Existing-File Behavior")
        collision_lbl.setStyleSheet("font-weight: 600;")
        collision_row.addWidget(collision_lbl)
        collision_row.addStretch()

        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItem("Rename automatically (safe)", OverwriteBehavior.RENAME.value)
        self.overwrite_combo.addItem("Overwrite existing file", OverwriteBehavior.OVERWRITE.value)
        self.overwrite_combo.addItem("Skip if file exists", OverwriteBehavior.SKIP.value)
        collision_row.addWidget(self.overwrite_combo)
        s_lay.addLayout(collision_row)

        self.sanitize_check = QCheckBox("Automatic safe filename sanitization (recommended)")
        s_lay.addWidget(self.sanitize_check)
        self._layout.addWidget(storage_card)

        # Card 2: Media & Download Defaults
        media_card = self._make_card("MEDIA, QUEUE & NETWORK DEFAULTS")
        m_lay = media_card.layout()

        fmt_row = QHBoxLayout()
        fmt_lbl = QLabel("Default Media Format")
        fmt_lbl.setStyleSheet("font-weight: 600;")
        fmt_row.addWidget(fmt_lbl)
        fmt_row.addStretch()
        self.format_combo = QComboBox()
        for label, value in DEFAULT_FORMAT_PRESETS:
            self.format_combo.addItem(label, value)
        fmt_row.addWidget(self.format_combo)
        m_lay.addLayout(fmt_row)

        qual_row = QHBoxLayout()
        qual_lbl = QLabel("Default Video Quality Preference")
        qual_lbl.setStyleSheet("font-weight: 600;")
        qual_row.addWidget(qual_lbl)
        qual_row.addStretch()
        self.quality_combo = QComboBox()
        for q in DEFAULT_QUALITY_OPTIONS:
            self.quality_combo.addItem(q.upper() if q != "best" else "Best Available", q)
        qual_row.addWidget(self.quality_combo)
        m_lay.addLayout(qual_row)

        conc_row = QHBoxLayout()
        conc_lbl = QLabel("Concurrent Downloads (1-5)")
        conc_lbl.setStyleSheet("font-weight: 600;")
        conc_row.addWidget(conc_lbl)
        conc_row.addStretch()
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(MIN_CONCURRENT_DOWNLOADS, MAX_CONCURRENT_DOWNLOADS)
        conc_row.addWidget(self.concurrency_spin)
        m_lay.addLayout(conc_row)

        self.mp3_check = QCheckBox("Auto-convert extracted audio to MP3 (requires FFmpeg)")
        m_lay.addWidget(self.mp3_check)

        self.ipv4_check = QCheckBox("Prefer IPv4 networking (avoids stalls on broken dual-stack IPv6 networks)")
        m_lay.addWidget(self.ipv4_check)
        self._layout.addWidget(media_card)

        # Card 3: Appearance
        theme_card = self._make_card("APPEARANCE")
        t_lay = theme_card.layout()
        theme_row = QHBoxLayout()
        theme_lbl = QLabel("Interface Theme")
        theme_lbl.setStyleSheet("font-weight: 600;")
        theme_row.addWidget(theme_lbl)
        theme_row.addStretch()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark Theme (Default)", ThemeMode.DARK.value)
        self.theme_combo.addItem("Light Theme", ThemeMode.LIGHT.value)
        theme_row.addWidget(self.theme_combo)
        t_lay.addLayout(theme_row)
        self._layout.addWidget(theme_card)

        # Action Buttons
        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.setIcon(make_icon("check", "#ffffff", 16))
        self.save_btn.clicked.connect(self._save_settings)
        btn_row.addWidget(self.save_btn)

        self.reset_btn = QPushButton("Discard Changes")
        self.reset_btn.setObjectName("GhostButton")
        self.reset_btn.clicked.connect(self.load_from_manager)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch()
        self._layout.addLayout(btn_row)

        # Card 4: Dependency Manager & Diagnostics
        deps_card = self._make_card("COMPONENTS & DIAGNOSTICS")
        d_lay = deps_card.layout()

        deps_top = QHBoxLayout()
        deps_desc = QLabel(
            "Check built-in components and download FFmpeg automatically for high-quality video and audio."
        )
        deps_desc.setObjectName("MutedLabel")
        deps_desc.setWordWrap(True)
        deps_top.addWidget(deps_desc, 1)

        self.download_ffmpeg_btn = QPushButton("Download FFmpeg")
        self.download_ffmpeg_btn.setObjectName("PrimaryButton")
        self.download_ffmpeg_btn.setIcon(make_icon("download", "#ffffff", 14))
        self.download_ffmpeg_btn.clicked.connect(self._on_download_ffmpeg_clicked)
        self.download_ffmpeg_btn.setVisible(False)
        deps_top.addWidget(self.download_ffmpeg_btn)

        self.recheck_btn = QPushButton("Re-check")
        self.recheck_btn.setObjectName("GhostButton")
        self.recheck_btn.setIcon(make_icon("retry", "#cbd5e1", 14))
        self.recheck_btn.clicked.connect(self.refresh_dependencies)
        deps_top.addWidget(self.recheck_btn)

        self.diag_btn = QPushButton("Diagnostics...")
        self.diag_btn.setObjectName("GhostButton")
        self.diag_btn.clicked.connect(self._open_diagnostics)
        deps_top.addWidget(self.diag_btn)
        d_lay.addLayout(deps_top)

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
        self.deps_list_layout.setSpacing(8)
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

    def _make_card(self, section_title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        lbl = QLabel(section_title)
        lbl.setObjectName("SectionTitle")
        lay.addWidget(lbl)
        return card

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
            lay.setContentsMargins(12, 10, 12, 10)
            lay.setSpacing(4)

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
