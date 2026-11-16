"""Friendly optional prompt shown when FFmpeg is not yet installed."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from link_downloader.services.download_manager import DownloadManager
from link_downloader.ui.styles.theme import make_icon


class FfmpegPromptDialog(QDialog):
    """Guides non-technical users to install FFmpeg in one click or skip for now."""

    def __init__(self, manager: DownloadManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._signals_connected = False

        self.setWindowTitle("Recommended Component: FFmpeg")
        self.setModal(True)
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(make_icon("download", "#818cf8", 28).pixmap(28, 28))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        top_row.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        title = QLabel("Download FFmpeg?")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        text_col.addWidget(title)

        self.message_label = QLabel(
            "FFmpeg is recommended for merging high-quality video and converting audio."
        )
        self.message_label.setWordWrap(True)
        text_col.addWidget(self.message_label)

        sub_note = QLabel(
            "Prism Link Downloader can download FFmpeg automatically into your app folder—no extra setup needed."
        )
        sub_note.setObjectName("MutedLabel")
        sub_note.setWordWrap(True)
        text_col.addWidget(sub_note)

        top_row.addLayout(text_col, 1)
        root.addLayout(top_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setObjectName("MutedLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        root.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.skip_btn = QPushButton("Skip for now")
        self.skip_btn.setObjectName("GhostButton")
        self.skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.skip_btn)

        self.download_btn = QPushButton("Download FFmpeg")
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setIcon(make_icon("download", "#ffffff", 15))
        self.download_btn.clicked.connect(self._on_download_clicked)
        btn_row.addWidget(self.download_btn)

        root.addLayout(btn_row)

        self._connect_signals()
        self.finished.connect(self._disconnect_signals)

        if self._manager.is_installing_ffmpeg():
            self._show_downloading_state(0, "Downloading FFmpeg...")

    def _connect_signals(self) -> None:
        if self._signals_connected:
            return
        self._manager.signals.ffmpeg_install_progress.connect(self._on_progress)
        self._manager.signals.ffmpeg_install_finished.connect(self._on_finished)
        self._manager.signals.ffmpeg_install_failed.connect(self._on_failed)
        self._signals_connected = True

    def _disconnect_signals(self) -> None:
        if not self._signals_connected:
            return
        try:
            self._manager.signals.ffmpeg_install_progress.disconnect(self._on_progress)
            self._manager.signals.ffmpeg_install_finished.disconnect(self._on_finished)
            self._manager.signals.ffmpeg_install_failed.disconnect(self._on_failed)
        except (RuntimeError, TypeError):
            pass
        self._signals_connected = False

    def _show_downloading_state(self, percent: int, message: str) -> None:
        self.download_btn.setEnabled(False)
        self.download_btn.setText("Downloading...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(percent)
        self.status_label.setObjectName("MutedLabel")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(message)
        self.status_label.setVisible(True)

    def _on_download_clicked(self) -> None:
        self._show_downloading_state(0, "Starting FFmpeg download...")
        started = self._manager.install_ffmpeg()
        if not started and not self._manager.is_installing_ffmpeg():
            self._on_failed("Unable to start FFmpeg download right now.")

    def _on_progress(self, percent: int, message: str) -> None:
        self._show_downloading_state(percent, message)

    def _on_finished(self, _path: str) -> None:
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(100)
        self.status_label.setObjectName("SuccessLabel")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText("FFmpeg is installed and ready.")
        self.status_label.setVisible(True)
        self.accept()

    def _on_failed(self, error_msg: str) -> None:
        self.download_btn.setEnabled(True)
        self.download_btn.setText("Download FFmpeg")
        self.progress_bar.setVisible(False)
        self.status_label.setObjectName("ErrorLabel")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(error_msg)
        self.status_label.setVisible(True)
