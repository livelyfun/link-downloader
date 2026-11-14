"""URL input card supporting drag-and-drop, clipboard paste, clear, and syntax validation."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from link_downloader.core.enums import EngineType
from link_downloader.core.exceptions import ValidationError
from link_downloader.core.validators import normalize_and_validate_url
from link_downloader.ui.styles.theme import make_icon


class UrlInputCard(QFrame):
    """Central URL entry area with validation feedback and link-type status badge."""

    analyze_requested = Signal(str)
    cleared = Signal()

    def __init__(self, *, allow_private: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAcceptDrops(True)
        self._allow_private = allow_private
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(make_icon("link", "#818cf8", 18).pixmap(18, 18))
        header.addWidget(icon_lbl)

        title = QLabel("Download from any supported URL or direct file link")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch()

        self.engine_badge = QLabel("Ready")
        self.engine_badge.setObjectName("BadgeInfo")
        self.engine_badge.setVisible(False)
        header.addWidget(self.engine_badge)
        layout.addLayout(header)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "Paste or drop a URL (YouTube, Vimeo, SoundCloud, direct .mp4/.pdf/.zip, or webpage)..."
        )
        self.url_input.setMinimumHeight(40)
        self.url_input.setClearButtonEnabled(False)
        self.url_input.textChanged.connect(self._on_text_changed)
        self.url_input.returnPressed.connect(self._trigger_analyze)
        input_row.addWidget(self.url_input, 1)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("GhostButton")
        self.clear_btn.setIcon(make_icon("clear", "#94a3b8", 16))
        self.clear_btn.setToolTip("Clear URL and reset preview")
        self.clear_btn.setMinimumHeight(40)
        self.clear_btn.clicked.connect(self.clear_all)
        self.clear_btn.setEnabled(False)
        input_row.addWidget(self.clear_btn)

        self.paste_btn = QPushButton("Paste")
        self.paste_btn.setObjectName("GhostButton")
        self.paste_btn.setIcon(make_icon("paste", "#cbd5e1", 16))
        self.paste_btn.setToolTip("Paste URL from clipboard")
        self.paste_btn.setMinimumHeight(40)
        self.paste_btn.clicked.connect(self.paste_from_clipboard)
        input_row.addWidget(self.paste_btn)

        self.analyze_btn = QPushButton("Analyze")
        self.analyze_btn.setObjectName("PrimaryButton")
        self.analyze_btn.setIcon(make_icon("search", "#ffffff", 16))
        self.analyze_btn.setToolTip("Analyze URL and detect available formats or file details")
        self.analyze_btn.setMinimumHeight(40)
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.clicked.connect(self._trigger_analyze)
        input_row.addWidget(self.analyze_btn)

        layout.addLayout(input_row)

        self.feedback_label = QLabel("")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setVisible(False)
        layout.addWidget(self.feedback_label)

    def set_url(self, url: str) -> None:
        self.url_input.setText(url.strip())

    def paste_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text().strip()
        if text:
            self.url_input.setText(text)
            self.url_input.setFocus()

    def clear_all(self) -> None:
        self.url_input.clear()
        self.engine_badge.setVisible(False)
        self.feedback_label.setVisible(False)
        self.url_input.setFocus()
        self.cleared.emit()

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.url_input.setEnabled(not loading)
        self.paste_btn.setEnabled(not loading)
        self.clear_btn.setEnabled(not loading and bool(self.url_input.text().strip()))
        self.analyze_btn.setText("Analyzing..." if loading else "Analyze")
        self._update_button_state()

    def set_error(self, message: str) -> None:
        self.engine_badge.setVisible(False)
        self.feedback_label.setObjectName("ErrorLabel")
        self.feedback_label.style().unpolish(self.feedback_label)
        self.feedback_label.style().polish(self.feedback_label)
        self.feedback_label.setText(message)
        self.feedback_label.setVisible(True)

    def set_detected_engine(self, engine_type: EngineType, label: str) -> None:
        self.engine_badge.setText(label)
        self.engine_badge.setObjectName(
            "BadgeSuccess" if engine_type == EngineType.DIRECT_HTTP else "BadgeInfo"
        )
        self.engine_badge.style().unpolish(self.engine_badge)
        self.engine_badge.style().polish(self.engine_badge)
        self.engine_badge.setVisible(True)

    def _on_text_changed(self, text: str) -> None:
        stripped = text.strip()
        self.clear_btn.setEnabled(bool(stripped) and not self._loading)
        self.engine_badge.setVisible(False)

        if not stripped:
            self.feedback_label.setVisible(False)
            self._update_button_state()
            return

        try:
            normalize_and_validate_url(stripped, allow_private=self._allow_private, strict_dns=False)
            self.feedback_label.setObjectName("MutedLabel")
            self.feedback_label.style().unpolish(self.feedback_label)
            self.feedback_label.style().polish(self.feedback_label)
            self.feedback_label.setText("Valid HTTP/HTTPS URL — press Enter or click Analyze.")
            self.feedback_label.setVisible(True)
        except ValidationError as exc:
            self.feedback_label.setObjectName("ErrorLabel")
            self.feedback_label.style().unpolish(self.feedback_label)
            self.feedback_label.style().polish(self.feedback_label)
            self.feedback_label.setText(exc.message)
            self.feedback_label.setVisible(True)

        self._update_button_state()

    def _update_button_state(self) -> None:
        stripped = self.url_input.text().strip()
        if self._loading or not stripped:
            self.analyze_btn.setEnabled(False)
            return
        try:
            normalize_and_validate_url(stripped, allow_private=self._allow_private, strict_dns=False)
            self.analyze_btn.setEnabled(True)
        except ValidationError:
            self.analyze_btn.setEnabled(False)

    def _trigger_analyze(self) -> None:
        stripped = self.url_input.text().strip()
        if not stripped or self._loading:
            return
        try:
            normalized = normalize_and_validate_url(
                stripped,
                allow_private=self._allow_private,
                strict_dns=False,
            )
        except ValidationError as exc:
            self.set_error(exc.message)
            return
        self.feedback_label.setVisible(False)
        self.analyze_requested.emit(normalized)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if urls:
                self.set_url(urls[0].toString())
                event.acceptProposedAction()
                return
        if mime.hasText():
            text = mime.text().strip()
            if text:
                self.set_url(text.splitlines()[0].strip())
                event.acceptProposedAction()
