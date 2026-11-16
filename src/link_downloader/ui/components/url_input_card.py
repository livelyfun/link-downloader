"""Responsive neumorphic URL command card supporting Quick Download and Inspect."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QComboBox,
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
    """Responsive URL command bar with preset picker, Inspect, and Quick Download."""

    analyze_requested = Signal(str)
    quick_download_requested = Signal(str, str)
    cleared = Signal()

    def __init__(self, *, allow_private: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAcceptDrops(True)
        self._allow_private = allow_private
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Row 1: URL input + Paste + Clear
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        link_icon = QLabel()
        link_icon.setPixmap(make_icon("link", "#2563eb", 16).pixmap(16, 16))
        input_row.addWidget(link_icon)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "Paste or drop any link (YouTube, Vimeo, SoundCloud, direct .mp4/.pdf/.zip, or webpage)..."
        )
        self.url_input.setMinimumHeight(36)
        self.url_input.setClearButtonEnabled(False)
        self.url_input.textChanged.connect(self._on_text_changed)
        self.url_input.returnPressed.connect(self._trigger_analyze)
        input_row.addWidget(self.url_input, 1)

        self.paste_btn = QPushButton("Paste")
        self.paste_btn.setObjectName("GhostButton")
        self.paste_btn.setIcon(make_icon("paste", "#475569", 14))
        self.paste_btn.setToolTip("Paste URL from clipboard (Ctrl+V)")
        self.paste_btn.setMinimumHeight(36)
        self.paste_btn.clicked.connect(self.paste_from_clipboard)
        input_row.addWidget(self.paste_btn)

        self.clear_btn = QPushButton()
        self.clear_btn.setObjectName("GhostButton")
        self.clear_btn.setIcon(make_icon("clear", "#475569", 14))
        self.clear_btn.setToolTip("Clear URL and dismiss preview")
        self.clear_btn.setMinimumHeight(36)
        self.clear_btn.setFixedWidth(38)
        self.clear_btn.clicked.connect(self.clear_all)
        self.clear_btn.setEnabled(False)
        input_row.addWidget(self.clear_btn)

        layout.addLayout(input_row)

        # Row 2: Preset selector + Inspect + Quick Download (responsive)
        self._ctrl_box = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._ctrl_box.setSpacing(8)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        self._preset_lbl = QLabel("Quick Preset:")
        self._preset_lbl.setObjectName("MutedLabel")
        preset_row.addWidget(self._preset_lbl)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Best Quality", "best")
        self.preset_combo.addItem("1080p HD", "1080p")
        self.preset_combo.addItem("720p HD", "720p")
        self.preset_combo.addItem("480p SD", "480p")
        self.preset_combo.addItem("Audio Only (MP3)", "audio")
        self.preset_combo.setMinimumHeight(32)
        preset_row.addWidget(self.preset_combo)
        preset_row.addStretch()
        self._ctrl_box.addLayout(preset_row, 1)

        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)
        self.analyze_btn = QPushButton("Inspect Formats")
        self.analyze_btn.setObjectName("GhostButton")
        self.analyze_btn.setIcon(make_icon("sliders", "#475569", 14))
        self.analyze_btn.setToolTip("Inspect title, formats, and file size before downloading (Enter)")
        self.analyze_btn.setMinimumHeight(34)
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.clicked.connect(self._trigger_analyze)
        btns_row.addWidget(self.analyze_btn)

        self.quick_download_btn = QPushButton("Quick Download")
        self.quick_download_btn.setObjectName("PrimaryButton")
        self.quick_download_btn.setIcon(make_icon("bolt", "#ffffff", 14))
        self.quick_download_btn.setToolTip("Download immediately using the selected Quick Preset")
        self.quick_download_btn.setMinimumHeight(34)
        self.quick_download_btn.setEnabled(False)
        self.quick_download_btn.clicked.connect(self._trigger_quick_download)
        btns_row.addWidget(self.quick_download_btn)
        self._ctrl_box.addLayout(btns_row)

        layout.addLayout(self._ctrl_box)

        # Row 3: Dedicated validation feedback & detected engine status row (avoids squishing controls)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self.engine_badge = QLabel("Ready")
        self.engine_badge.setObjectName("BadgeInfo")
        self.engine_badge.setVisible(False)
        status_row.addWidget(self.engine_badge)

        self.feedback_label = QLabel("")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setVisible(False)
        status_row.addWidget(self.feedback_label, 1)

        layout.addLayout(status_row)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        w = event.size().width()
        narrow = w < 540
        self._preset_lbl.setVisible(not narrow)
        if not self._loading:
            self.analyze_btn.setText("Inspect" if narrow else "Inspect Formats")
        direction = (
            QBoxLayout.Direction.TopToBottom
            if w < 460
            else QBoxLayout.Direction.LeftToRight
        )
        if self._ctrl_box.direction() != direction:
            self._ctrl_box.setDirection(direction)

    def set_url(self, url: str) -> None:
        self.url_input.setText(url.strip())

    def selected_preset(self) -> str:
        return str(self.preset_combo.currentData() or "best")

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
        self.preset_combo.setEnabled(not loading)
        self.clear_btn.setEnabled(not loading and bool(self.url_input.text().strip()))
        narrow = self.width() < 540
        self.analyze_btn.setText("Inspecting..." if loading else ("Inspect" if narrow else "Inspect Formats"))
        self.quick_download_btn.setText("Resolving..." if loading else "Quick Download")
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
            self.feedback_label.setText("Valid HTTP/HTTPS URL — press Enter to inspect or click Quick Download.")
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
        valid = False
        if not self._loading and stripped:
            try:
                normalize_and_validate_url(stripped, allow_private=self._allow_private, strict_dns=False)
                valid = True
            except ValidationError:
                valid = False
        self.analyze_btn.setEnabled(valid)
        self.quick_download_btn.setEnabled(valid)

    def _validate_current(self) -> str | None:
        stripped = self.url_input.text().strip()
        if not stripped or self._loading:
            return None
        try:
            normalized = normalize_and_validate_url(
                stripped,
                allow_private=self._allow_private,
                strict_dns=False,
            )
        except ValidationError as exc:
            self.set_error(exc.message)
            return None
        self.feedback_label.setVisible(False)
        return normalized

    def _trigger_analyze(self) -> None:
        normalized = self._validate_current()
        if normalized is not None:
            self.analyze_requested.emit(normalized)

    def _trigger_quick_download(self) -> None:
        normalized = self._validate_current()
        if normalized is not None:
            self.quick_download_requested.emit(normalized, self.selected_preset())

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
