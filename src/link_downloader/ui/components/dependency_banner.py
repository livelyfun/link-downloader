"""Dismissible top banner warning about missing recommended/required dependencies."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from link_downloader.core.models import DependencyStatus
from link_downloader.ui.styles.theme import make_icon


class DependencyBanner(QFrame):
    """Informs users when external tools like FFmpeg or a JS runtime are unavailable."""

    inspect_requested = Signal()

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
        self._title = QLabel("Optional/Recommended dependencies unavailable")
        self._title.setStyleSheet("font-weight: 600; color: #fbbf24;")
        self._detail = QLabel("")
        self._detail.setObjectName("MutedLabel")
        self._detail.setWordWrap(True)
        text_col.addWidget(self._title)
        text_col.addWidget(self._detail)
        root.addLayout(text_col, 1)

        self._inspect_btn = QPushButton("View Guidance")
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
            return
        names = ", ".join(m.name for m in missing)
        self._title.setText(f"Missing tools or components: {names}")
        self._detail.setText(missing[0].impact)
        self.setVisible(True)
