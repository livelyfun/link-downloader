"""Dismissible top banner warning about missing recommended/required dependencies."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from link_downloader.core.models import DependencyStatus
from link_downloader.ui.styles.theme import make_icon


class DependencyBanner(QFrame):
    """Informs users cleanly when recommended components like FFmpeg are not yet installed."""

    inspect_requested = Signal()
    download_ffmpeg_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("BannerWarning")
        self.setVisible(False)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(make_icon("warning", "#fbbf24", 20).pixmap(20, 20))
        root.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._title = QLabel("FFmpeg is not installed yet")
        self._title.setStyleSheet("font-weight: 600; color: #fbbf24;")
        self._detail = QLabel("")
        self._detail.setObjectName("MutedLabel")
        self._detail.setWordWrap(True)
        text_col.addWidget(self._title)
        text_col.addWidget(self._detail)
        root.addLayout(text_col, 1)

        self.download_ffmpeg_btn = QPushButton("Download FFmpeg")
        self.download_ffmpeg_btn.setObjectName("PrimaryButton")
        self.download_ffmpeg_btn.setIcon(make_icon("download", "#ffffff", 14))
        self.download_ffmpeg_btn.clicked.connect(self.download_ffmpeg_requested.emit)
        self.download_ffmpeg_btn.setVisible(False)
        root.addWidget(self.download_ffmpeg_btn)

        self._inspect_btn = QPushButton("Details")
        self._inspect_btn.setObjectName("GhostButton")
        self._inspect_btn.clicked.connect(self.inspect_requested.emit)
        root.addWidget(self._inspect_btn)

        self._dismiss_btn = QPushButton("Dismiss")
        self._dismiss_btn.setObjectName("GhostButton")
        self._dismiss_btn.clicked.connect(self.hide)
        root.addWidget(self._dismiss_btn)

    def update_statuses(self, missing: list[DependencyStatus]) -> None:
        if not missing:
            self.setVisible(False)
            self.download_ffmpeg_btn.setVisible(False)
            return
        ffmpeg_missing = any(m.name in {"FFmpeg", "FFprobe"} for m in missing)
        self.download_ffmpeg_btn.setVisible(ffmpeg_missing)
        if ffmpeg_missing and len(missing) == 1:
            self._title.setText("FFmpeg is recommended")
            self._detail.setText(
                "FFmpeg is recommended for merging high-quality video and converting audio."
            )
        else:
            names = ", ".join(m.name for m in missing)
            self._title.setText(f"Recommended setup: {names}")
            self._detail.setText(missing[0].impact)
        self.setVisible(True)

    def set_installing(self, installing: bool, percent: int = 0, message: str = "") -> None:
        """Update banner button and detail text while one-click FFmpeg download runs."""
        if installing:
            self.setVisible(True)
            self.download_ffmpeg_btn.setVisible(True)
            self.download_ffmpeg_btn.setEnabled(False)
            self.download_ffmpeg_btn.setText(f"Downloading... ({percent}%)")
            if message:
                self._detail.setText(message)
        else:
            self.download_ffmpeg_btn.setEnabled(True)
            self.download_ffmpeg_btn.setText("Download FFmpeg")

    def set_error(self, message: str) -> None:
        """Display a non-technical error message in the banner and allow retry."""
        self.setVisible(True)
        self.download_ffmpeg_btn.setVisible(True)
        self.download_ffmpeg_btn.setEnabled(True)
        self.download_ffmpeg_btn.setText("Download FFmpeg")
        self._title.setText("FFmpeg download could not complete")
        self._detail.setText(message)
