"""Reusable empty-state card widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from link_downloader.ui.styles.theme import make_icon


class EmptyStateWidget(QFrame):
    """Displays an informative placeholder when a list or view has no items."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        *,
        icon_name: str = "download",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 42, 32, 42)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setPixmap(make_icon(icon_name, "#64748b", 36).pixmap(36, 36))

        self._title_label = QLabel(title)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setStyleSheet("font-size: 15px; font-weight: 600;")

        self._subtitle_label = QLabel(subtitle)
        self._subtitle_label.setObjectName("MutedLabel")
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle_label.setWordWrap(True)

        layout.addWidget(self._icon_label)
        layout.addWidget(self._title_label)
        layout.addWidget(self._subtitle_label)
