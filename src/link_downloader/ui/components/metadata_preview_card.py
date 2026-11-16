"""Responsive neumorphic media inspector and format selection panel."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from link_downloader.core.enums import EngineType, FormatKind
from link_downloader.core.models import (
    FormatOption,
    ResourceMetadata,
    format_bytes,
    format_duration,
)
from link_downloader.ui.styles.theme import make_icon


def _format_count(n: int | None) -> str | None:
    if n is None or n < 0:
        return None
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B views"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K views"
    return f"{n} views"


class MetadataPreviewCard(QFrame):
    """Responsive inspector switching cleanly between side-by-side and stacked layouts."""

    download_requested = Signal(object, object, str)  # ResourceMetadata, FormatOption, custom_name
    closed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setVisible(False)

        self._metadata: ResourceMetadata | None = None
        self._ffmpeg_available = True
        self._current_filter = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Header strip: Title + dismiss icon button
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self.title_label = QLabel("")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 700;")
        header_row.addWidget(self.title_label, 1)

        self.close_btn = QPushButton()
        self.close_btn.setObjectName("IconButton")
        self.close_btn.setIcon(make_icon("clear", "#64748b", 14))
        self.close_btn.setToolTip("Collapse inspector")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.clicked.connect(self._on_close_clicked)
        header_row.addWidget(self.close_btn)
        root.addLayout(header_row)

        # Responsive split: side-by-side when >= 560px wide, stacked below 560px
        self._split_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._split_layout.setSpacing(14)

        self._left_pane = QWidget()
        self._left_pane.setFixedWidth(196)
        left_col = QVBoxLayout(self._left_pane)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(6)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(192, 108)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet(
            "background-color: #dbe4f0; border: 1px solid #c1cde0; border-radius: 10px;"
        )
        left_col.addWidget(self.thumb_label)

        self.sub_label = QLabel("")
        self.sub_label.setObjectName("MutedLabel")
        self.sub_label.setWordWrap(True)
        left_col.addWidget(self.sub_label)

        badges_wrap = QVBoxLayout()
        badges_wrap.setSpacing(4)
        badges_top = QHBoxLayout()
        badges_top.setSpacing(4)
        self.platform_badge = QLabel("")
        self.platform_badge.setObjectName("BadgeInfo")
        self.duration_or_size_badge = QLabel("")
        self.duration_or_size_badge.setObjectName("BadgeInfo")
        badges_top.addWidget(self.platform_badge)
        badges_top.addWidget(self.duration_or_size_badge)
        badges_top.addStretch()
        badges_wrap.addLayout(badges_top)

        self.extra_badge = QLabel("")
        self.extra_badge.setObjectName("BadgeSuccess")
        badges_wrap.addWidget(self.extra_badge)
        left_col.addLayout(badges_wrap)

        self.desc_label = QLabel("")
        self.desc_label.setObjectName("MutedLabel")
        self.desc_label.setWordWrap(True)
        self.desc_label.setMaximumHeight(34)
        left_col.addWidget(self.desc_label)
        left_col.addStretch()

        self._split_layout.addWidget(self._left_pane)

        # Right pane: Format Selector OR Direct Spec Sheet
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(8)

        # Direct file details grid (shown only for EngineType.DIRECT_HTTP)
        self.direct_details_card = QFrame()
        self.direct_details_card.setObjectName("SubCard")
        grid = QGridLayout(self.direct_details_card)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        self._direct_fields: dict[str, QLabel] = {}
        field_labels = [
            ("filename", "Filename", 0, 0),
            ("category", "Type", 0, 1),
            ("content_type", "MIME", 1, 0),
            ("size", "Size", 1, 1),
            ("host", "Host", 2, 0),
            ("resume", "Resume", 2, 1),
        ]
        for key, label_text, row_idx, col_idx in field_labels:
            cell = QHBoxLayout()
            cell.setSpacing(6)
            lbl = QLabel(f"{label_text}:")
            lbl.setObjectName("MutedLabel")
            val = QLabel("—")
            val.setStyleSheet("font-weight: 600;")
            val.setWordWrap(True)
            cell.addWidget(lbl)
            cell.addWidget(val, 1)
            grid.addLayout(cell, row_idx, col_idx)
            self._direct_fields[key] = val
        right_col.addWidget(self.direct_details_card)

        # Media format selection section (shown only for EngineType.YTDLP)
        self.media_formats_box = QWidget()
        fmt_layout = QVBoxLayout(self.media_formats_box)
        fmt_layout.setContentsMargins(0, 0, 0, 0)
        fmt_layout.setSpacing(6)

        filter_row_box = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        filter_row_box.setSpacing(6)
        self._filter_box = filter_row_box

        chips_row = QHBoxLayout()
        chips_row.setSpacing(4)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        for key, text in [
            ("all", "All"),
            (FormatKind.VIDEO_AUDIO.value, "Video + Audio"),
            (FormatKind.VIDEO_ONLY.value, "Video Only"),
            (FormatKind.AUDIO_ONLY.value, "Audio Only"),
        ]:
            btn = QPushButton(text)
            btn.setObjectName("FilterChip")
            btn.setCheckable(True)
            if key == "all":
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked=False, k=key: self._set_filter(k))
            self._filter_group.addButton(btn)
            chips_row.addWidget(btn)
        chips_row.addStretch()
        filter_row_box.addLayout(chips_row, 1)

        self.quality_jump_combo = QComboBox()
        self.quality_jump_combo.addItem("Auto Best", "best")
        self.quality_jump_combo.addItem("1080p", "1080")
        self.quality_jump_combo.addItem("720p", "720")
        self.quality_jump_combo.addItem("480p", "480")
        self.quality_jump_combo.addItem("Audio / MP3", "audio")
        self.quality_jump_combo.currentIndexChanged.connect(self._on_quality_jump)
        filter_row_box.addWidget(self.quality_jump_combo)
        fmt_layout.addLayout(filter_row_box)

        self.format_list = QListWidget()
        self.format_list.setMinimumHeight(115)
        self.format_list.setMaximumHeight(160)
        self.format_list.currentItemChanged.connect(self._on_format_selected)
        fmt_layout.addWidget(self.format_list)

        self.ffmpeg_note_label = QLabel("")
        self.ffmpeg_note_label.setObjectName("BadgeWarning")
        self.ffmpeg_note_label.setWordWrap(True)
        self.ffmpeg_note_label.setVisible(False)
        fmt_layout.addWidget(self.ffmpeg_note_label)

        right_col.addWidget(self.media_formats_box, 1)

        # Save-as + Download CTA row aligned under right column
        self._action_box = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._action_box.setSpacing(8)

        save_wrap = QHBoxLayout()
        save_wrap.setSpacing(6)
        name_lbl = QLabel("Save as:")
        name_lbl.setObjectName("MutedLabel")
        save_wrap.addWidget(name_lbl)

        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("Automatic safe filename")
        self.filename_edit.setMinimumWidth(100)
        save_wrap.addWidget(self.filename_edit, 1)
        self._action_box.addLayout(save_wrap, 1)

        self.download_btn = QPushButton("Download")
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setIcon(make_icon("download", "#ffffff", 15))
        self.download_btn.setMinimumHeight(34)
        self.download_btn.clicked.connect(self._emit_download)
        self._action_box.addWidget(self.download_btn)

        right_col.addLayout(self._action_box)
        self._split_layout.addLayout(right_col, 1)
        root.addLayout(self._split_layout)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        w = event.size().width()
        stacked = w < 580
        if stacked:
            self._split_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self._left_pane.setMinimumWidth(0)
            self._left_pane.setMaximumWidth(16_777_215)
        else:
            self._split_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self._left_pane.setFixedWidth(196)

        narrow = w < 520
        sub_dir = QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        self._filter_box.setDirection(sub_dir)
        self._action_box.setDirection(sub_dir)

    def _on_close_clicked(self) -> None:
        self.setVisible(False)
        self.closed.emit()

    def set_metadata(
        self,
        metadata: ResourceMetadata,
        thumbnail_bytes: bytes | None = None,
        *,
        ffmpeg_available: bool = True,
    ) -> None:
        self._metadata = metadata
        self._ffmpeg_available = ffmpeg_available
        self.title_label.setText(metadata.title)
        self.filename_edit.setText(metadata.filename or "")

        if thumbnail_bytes:
            pixmap = QPixmap()
            if pixmap.loadFromData(thumbnail_bytes):
                scaled = pixmap.scaled(
                    self.thumb_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.thumb_label.setPixmap(scaled)
            else:
                self._set_fallback_thumb(metadata.engine_type)
        else:
            self._set_fallback_thumb(metadata.engine_type)

        self.platform_badge.setText(metadata.source_platform)
        is_direct = metadata.engine_type == EngineType.DIRECT_HTTP

        if is_direct:
            self.sub_label.setText(f"From {metadata.hostname}")
            self.duration_or_size_badge.setText(
                format_bytes(metadata.total_bytes) if metadata.total_bytes else "Streamed"
            )
            self.extra_badge.setText(
                "Resume Supported" if metadata.supports_resume else "Single-stream"
            )
            self.extra_badge.setObjectName("BadgeSuccess" if metadata.supports_resume else "BadgeWarning")
            self.extra_badge.style().unpolish(self.extra_badge)
            self.extra_badge.style().polish(self.extra_badge)
            self.desc_label.setVisible(False)

            self._direct_fields["filename"].setText(metadata.filename or "—")
            self._direct_fields["category"].setText(
                f"{metadata.file_category or 'File'} ({metadata.file_extension or 'raw'})"
            )
            self._direct_fields["content_type"].setText(metadata.content_type or "Unknown")
            self._direct_fields["size"].setText(
                format_bytes(metadata.total_bytes) if metadata.total_bytes is not None else "Unknown"
            )
            self._direct_fields["host"].setText(metadata.hostname)
            self._direct_fields["resume"].setText(
                "HTTP Range Supported" if metadata.supports_resume else "Single-stream"
            )

            self.direct_details_card.setVisible(True)
            self.media_formats_box.setVisible(False)
            self.download_btn.setText("Download File")
            self.download_btn.setEnabled(True)
        else:
            uploader_parts = [p for p in [metadata.uploader, _format_count(metadata.view_count)] if p]
            self.sub_label.setText(" · ".join(uploader_parts) if uploader_parts else metadata.hostname)
            self.duration_or_size_badge.setText(
                format_duration(metadata.duration_seconds)
                if metadata.duration_seconds is not None
                else "Media"
            )
            if metadata.is_playlist and metadata.playlist_count:
                self.extra_badge.setText(f"Playlist ({metadata.playlist_count} items)")
            else:
                self.extra_badge.setText(f"{len(metadata.formats)} formats")
            self.extra_badge.setObjectName("BadgeInfo")
            self.extra_badge.style().unpolish(self.extra_badge)
            self.extra_badge.style().polish(self.extra_badge)
            self.extra_badge.setVisible(True)

            if metadata.description:
                snippet = " ".join(metadata.description.split())[:120]
                self.desc_label.setText(snippet)
                self.desc_label.setVisible(True)
            else:
                self.desc_label.setVisible(False)

            self.direct_details_card.setVisible(False)
            self.media_formats_box.setVisible(True)
            self.download_btn.setText("Download Selected")
            self.quality_jump_combo.blockSignals(True)
            self.quality_jump_combo.setCurrentIndex(0)
            self.quality_jump_combo.blockSignals(False)
            self._populate_formats()

        self.setVisible(True)

    def _set_fallback_thumb(self, engine_type: EngineType) -> None:
        icon_name = "file" if engine_type == EngineType.DIRECT_HTTP else "download"
        self.thumb_label.setPixmap(make_icon(icon_name, "#2563eb", 34).pixmap(34, 34))

    def _set_filter(self, filter_key: str) -> None:
        self._current_filter = filter_key
        self._populate_formats()

    def _on_quality_jump(self, _index: int) -> None:
        target = str(self.quality_jump_combo.currentData() or "best")
        if target == "audio":
            audio_btn = next(
                (b for b in self._filter_group.buttons() if "Audio Only" in b.text()), None
            )
            if audio_btn is not None:
                audio_btn.setChecked(True)
                self._set_filter(FormatKind.AUDIO_ONLY.value)
                return
        elif target == "best":
            all_btn = next((b for b in self._filter_group.buttons() if b.text() == "All"), None)
            if all_btn is not None:
                all_btn.setChecked(True)
                self._set_filter("all")
                return

        if target in {"1080", "720", "480"}:
            all_btn = next((b for b in self._filter_group.buttons() if b.text() == "All"), None)
            if all_btn is not None and not all_btn.isChecked():
                all_btn.setChecked(True)
                self._set_filter("all")
            for idx in range(self.format_list.count()):
                item = self.format_list.item(idx)
                fmt: FormatOption = item.data(Qt.ItemDataRole.UserRole)
                if fmt and fmt.height is not None and str(fmt.height) == target:
                    self.format_list.setCurrentRow(idx)
                    return

    def _populate_formats(self) -> None:
        self.format_list.clear()
        if not self._metadata:
            self.download_btn.setEnabled(False)
            return

        for fmt in self._metadata.formats:
            if self._current_filter != "all" and fmt.kind.value != self._current_filter:
                continue
            suffix = "  [Needs FFmpeg]" if (fmt.requires_ffmpeg and not self._ffmpeg_available) else ""
            item = QListWidgetItem(f"{fmt.label}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, fmt)
            self.format_list.addItem(item)

        if self.format_list.count() > 0:
            self.format_list.setCurrentRow(0)
            self.download_btn.setEnabled(True)
        else:
            self.download_btn.setEnabled(False)
            self.ffmpeg_note_label.setVisible(False)

    def _on_format_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            self.ffmpeg_note_label.setVisible(False)
            return
        fmt: FormatOption = current.data(Qt.ItemDataRole.UserRole)
        if fmt and fmt.requires_ffmpeg and not self._ffmpeg_available:
            self.ffmpeg_note_label.setText(
                "FFmpeg is needed to merge this stream or convert to MP3. Install FFmpeg above or pick a combined format."
            )
            self.ffmpeg_note_label.setVisible(True)
        else:
            self.ffmpeg_note_label.setVisible(False)

    def selected_format(self) -> FormatOption | None:
        if self._metadata is None:
            return None
        if self._metadata.engine_type == EngineType.DIRECT_HTTP:
            return self._metadata.formats[0] if self._metadata.formats else None
        item = self.format_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _emit_download(self) -> None:
        if self._metadata is None:
            return
        fmt = self.selected_format()
        if fmt is None:
            return
        self.download_requested.emit(self._metadata, fmt, self.filename_edit.text().strip())
