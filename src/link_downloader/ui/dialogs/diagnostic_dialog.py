"""User-friendly component status and diagnostics dialog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from link_downloader.core.enums import DependencyCategory
from link_downloader.core.models import DependencyStatus, MigrationReport
from link_downloader.services.dependency_service import DependencyService
from link_downloader.ui.styles.theme import make_icon

if TYPE_CHECKING:
    from link_downloader.services.download_manager import DownloadManager


class DiagnosticDialog(QDialog):
    """Displays clear, non-technical component status and highlights one-click actions."""

    download_ffmpeg_requested = Signal()

    def __init__(
        self,
        dependencies: list[DependencyStatus],
        migration_report: MigrationReport,
        parent=None,
        *,
        manager: DownloadManager | None = None,
    ) -> None:
        super().__init__(parent)
        self._dependencies = list(dependencies)
        self._migration_report = migration_report
        self._manager = manager
        self._signals_connected = False

        self.setWindowTitle("App Diagnostics")
        self.resize(700, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        header = QLabel("App Components & Diagnostics")
        header.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(header)

        subtitle = QLabel(
            "All core download features are built in. Check optional enhancements or install FFmpeg in one click."
        )
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Highlighted One-Click FFmpeg Action Card
        self.ffmpeg_card = QFrame()
        self.ffmpeg_card.setObjectName("BannerWarning")
        f_lay = QVBoxLayout(self.ffmpeg_card)
        f_lay.setContentsMargins(14, 12, 14, 12)
        f_lay.setSpacing(8)

        f_top = QHBoxLayout()
        f_top.setSpacing(12)
        f_text_col = QVBoxLayout()
        f_text_col.setSpacing(2)
        self.ffmpeg_title = QLabel("FFmpeg Recommended")
        self.ffmpeg_title.setStyleSheet("font-weight: 700; color: #b45309;")
        self.ffmpeg_desc = QLabel(
            "FFmpeg is recommended for merging high-quality video and converting audio."
        )
        self.ffmpeg_desc.setObjectName("MutedLabel")
        self.ffmpeg_desc.setWordWrap(True)
        f_text_col.addWidget(self.ffmpeg_title)
        f_text_col.addWidget(self.ffmpeg_desc)
        f_top.addLayout(f_text_col, 1)

        self.download_ffmpeg_btn = QPushButton("Download FFmpeg")
        self.download_ffmpeg_btn.setObjectName("PrimaryButton")
        self.download_ffmpeg_btn.setIcon(make_icon("download", "#ffffff", 15))
        self.download_ffmpeg_btn.clicked.connect(self._on_download_ffmpeg_clicked)
        f_top.addWidget(self.download_ffmpeg_btn)
        f_lay.addLayout(f_top)

        self.ffmpeg_progress = QProgressBar()
        self.ffmpeg_progress.setRange(0, 100)
        self.ffmpeg_progress.setValue(0)
        self.ffmpeg_progress.setVisible(False)
        f_lay.addWidget(self.ffmpeg_progress)

        self.ffmpeg_status_label = QLabel("")
        self.ffmpeg_status_label.setObjectName("MutedLabel")
        self.ffmpeg_status_label.setWordWrap(True)
        self.ffmpeg_status_label.setVisible(False)
        f_lay.addWidget(self.ffmpeg_status_label)

        layout.addWidget(self.ffmpeg_card)

        # Component Checklist
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self._cards_layout = QVBoxLayout(scroll_content)
        self._cards_layout.setContentsMargins(0, 0, 4, 0)
        self._cards_layout.setSpacing(8)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        summary_lbl = QLabel("Shareable Summary")
        summary_lbl.setObjectName("SectionTitle")
        layout.addWidget(summary_lbl)

        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFixedHeight(120)
        self.text_area.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.text_area)

        btn_row = QHBoxLayout()
        self.copy_feedback = QLabel("")
        self.copy_feedback.setObjectName("SuccessLabel")
        btn_row.addWidget(self.copy_feedback)
        btn_row.addStretch()

        copy_btn = QPushButton("Copy Summary")
        copy_btn.setObjectName("GhostButton")
        copy_btn.clicked.connect(self._copy_report)
        btn_row.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("PrimaryButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        if self._manager is not None:
            self._connect_manager_signals()
            self.finished.connect(self._disconnect_manager_signals)

        self._render()

    def _connect_manager_signals(self) -> None:
        if self._manager is None or self._signals_connected:
            return
        self._manager.signals.ffmpeg_install_progress.connect(self._on_ffmpeg_progress)
        self._manager.signals.ffmpeg_install_finished.connect(self._on_ffmpeg_finished)
        self._manager.signals.ffmpeg_install_failed.connect(self._on_ffmpeg_failed)
        self._manager.signals.dependencies_changed.connect(self._refresh_from_manager)
        self._signals_connected = True

    def _disconnect_manager_signals(self) -> None:
        if self._manager is None or not self._signals_connected:
            return
        try:
            self._manager.signals.ffmpeg_install_progress.disconnect(self._on_ffmpeg_progress)
            self._manager.signals.ffmpeg_install_finished.disconnect(self._on_ffmpeg_finished)
            self._manager.signals.ffmpeg_install_failed.disconnect(self._on_ffmpeg_failed)
            self._manager.signals.dependencies_changed.disconnect(self._refresh_from_manager)
        except (RuntimeError, TypeError):
            pass
        self._signals_connected = False

    def _render(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        ffmpeg_missing = False
        for dep in self._dependencies:
            if dep.name == "FFmpeg" and not dep.available:
                ffmpeg_missing = True

            card = QFrame()
            card.setObjectName("SubCard")
            lay = QVBoxLayout(card)
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

            badge = QLabel(badge_text)
            badge.setObjectName(badge_obj)
            top.addWidget(badge)
            lay.addLayout(top)

            desc = QLabel(dep.impact)
            desc.setObjectName("MutedLabel")
            desc.setWordWrap(True)
            lay.addWidget(desc)

            if dep.available and dep.path:
                loc = QLabel(f"Location: {dep.path}")
                loc.setObjectName("MutedLabel")
                loc.setWordWrap(True)
                lay.addWidget(loc)
            elif not dep.available:
                hint = QLabel(dep.install_hint)
                hint.setObjectName("MutedLabel")
                hint.setWordWrap(True)
                lay.addWidget(hint)

            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch()
        self.ffmpeg_card.setVisible(ffmpeg_missing or (self._manager is not None and self._manager.is_installing_ffmpeg()))
        self.text_area.setPlainText(
            DependencyService.format_diagnostic_report(self._dependencies, self._migration_report)
        )

    def _refresh_from_manager(self) -> None:
        if self._manager is not None:
            self._dependencies = self._manager.check_dependencies()
            self._render()

    def _on_download_ffmpeg_clicked(self) -> None:
        self.download_ffmpeg_requested.emit()
        if self._manager is not None:
            self.download_ffmpeg_btn.setEnabled(False)
            self.download_ffmpeg_btn.setText("Downloading...")
            self.ffmpeg_progress.setVisible(True)
            self.ffmpeg_status_label.setObjectName("MutedLabel")
            self.ffmpeg_status_label.style().unpolish(self.ffmpeg_status_label)
            self.ffmpeg_status_label.style().polish(self.ffmpeg_status_label)
            self.ffmpeg_status_label.setText("Starting FFmpeg download...")
            self.ffmpeg_status_label.setVisible(True)
            self._manager.install_ffmpeg()

    def _on_ffmpeg_progress(self, percent: int, message: str) -> None:
        self.ffmpeg_card.setVisible(True)
        self.download_ffmpeg_btn.setEnabled(False)
        self.download_ffmpeg_btn.setText("Downloading...")
        self.ffmpeg_progress.setVisible(True)
        self.ffmpeg_progress.setValue(percent)
        self.ffmpeg_status_label.setText(message)
        self.ffmpeg_status_label.setVisible(True)

    def _on_ffmpeg_finished(self, _path: str) -> None:
        self.download_ffmpeg_btn.setEnabled(True)
        self.download_ffmpeg_btn.setText("Download FFmpeg")
        self.ffmpeg_progress.setValue(100)
        self.ffmpeg_status_label.setObjectName("SuccessLabel")
        self.ffmpeg_status_label.style().unpolish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.style().polish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.setText("FFmpeg is installed and ready.")
        self._refresh_from_manager()

    def _on_ffmpeg_failed(self, error_msg: str) -> None:
        self.download_ffmpeg_btn.setEnabled(True)
        self.download_ffmpeg_btn.setText("Download FFmpeg")
        self.ffmpeg_progress.setVisible(False)
        self.ffmpeg_status_label.setObjectName("ErrorLabel")
        self.ffmpeg_status_label.style().unpolish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.style().polish(self.ffmpeg_status_label)
        self.ffmpeg_status_label.setText(error_msg)
        self.ffmpeg_status_label.setVisible(True)

    def _copy_report(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text_area.toPlainText())
            self.copy_feedback.setText("Copied to clipboard")
