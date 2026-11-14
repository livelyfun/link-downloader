"""Metadata preview and format selection card for both media streams and direct files."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
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
    """Displays analyzed media/file metadata, selectable formats, and Download action."""

    download_requested = Signal(object, object, str)  # ResourceMetadata, FormatOption, custom_name

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setVisible(False)

        self._metadata: ResourceMetadata | None = None
        self._ffmpeg_available = True
        self._current_filter = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        # Header row: thumbnail + details
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(224, 126)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet(
            "background-color: #131620; border: 1px solid #2a3047; border-radius: 10px;"
        )
        top_row.addWidget(self.thumb_label)

        info_col = QVBoxLayout()
        info_col.setSpacing(6)

        self.title_label = QLabel("")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        info_col.addWidget(self.title_label)

        self.sub_label = QLabel("")
        self.sub_label.setObjectName("MutedLabel")
        self.sub_label.setWordWrap(True)
        info_col.addWidget(self.sub_label)

        self.badges_row = QHBoxLayout()
        self.badges_row.setSpacing(6)
        self.platform_badge = QLabel("")
        self.platform_badge.setObjectName("BadgeInfo")
        self.duration_or_size_badge = QLabel("")
        self.duration_or_size_badge.setObjectName("BadgeInfo")
        self.extra_badge = QLabel("")
        self.extra_badge.setObjectName("BadgeSuccess")
        self.badges_row.addWidget(self.platform_badge)
        self.badges_row.addWidget(self.duration_or_size_badge)
        self.badges_row.addWidget(self.extra_badge)
        self.badges_row.addStretch()
        info_col.addLayout(self.badges_row)

        self.desc_label = QLabel("")
        self.desc_label.setObjectName("MutedLabel")
        self.desc_label.setWordWrap(True)
        self.desc_label.setMaximumHeight(42)
        info_col.addWidget(self.desc_label)
        info_col.addStretch()

        top_row.addLayout(info_col, 1)
        root.addLayout(top_row)

        # Direct file details grid (shown only for EngineType.DIRECT_HTTP)
        self.direct_details_card = QFrame()
        self.direct_details_card.setObjectName("SubCard")
        grid = QGridLayout(self.direct_details_card)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)
        self._direct_fields: dict[str, QLabel] = {}
        field_labels = [
            ("filename", "Filename", 0, 0),
            ("category", "File Type", 0, 1),
            ("content_type", "Content-Type", 1, 0),
            ("size", "File Size", 1, 1),
            ("host", "Source Host", 2, 0),
            ("resume", "Resume Support", 2, 1),
        ]
        for key, label_text, row_idx, col_idx in field_labels:
            cell = QHBoxLayout()
            lbl = QLabel(f"{label_text}:")
            lbl.setObjectName("MutedLabel")
            val = QLabel("—")
            val.setStyleSheet("font-weight: 600;")
            cell.addWidget(lbl)
            cell.addWidget(val, 1)
            grid.addLayout(cell, row_idx, col_idx)
            self._direct_fields[key] = val
        root.addWidget(self.direct_details_card)

        # Media format selection section (shown only for EngineType.YTDLP)
        self.media_formats_box = QWidget()
        fmt_layout = QVBoxLayout(self.media_formats_box)
        fmt_layout.setContentsMargins(0, 0, 0, 0)
        fmt_layout.setSpacing(8)

        filter_row = QHBoxLayout()
        filter_lbl = QLabel("AVAILABLE FORMATS")
        filter_lbl.setObjectName("SectionTitle")
        filter_row.addWidget(filter_lbl)
        filter_row.addStretch()

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
            filter_row.addWidget(btn)
        fmt_layout.addLayout(filter_row)

        self.format_list = QListWidget()
        self.format_list.setMinimumHeight(150)
        self.format_list.setMaximumHeight(220)
        self.format_list.currentItemChanged.connect(self._on_format_selected)
        fmt_layout.addWidget(self.format_list)

        self.ffmpeg_note_label = QLabel("")
        self.ffmpeg_note_label.setObjectName("BadgeWarning")
        self.ffmpeg_note_label.setVisible(False)
        fmt_layout.addWidget(self.ffmpeg_note_label)

        root.addWidget(self.media_formats_box)

        # Optional custom filename + Download CTA row
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        name_lbl = QLabel("Save as:")
        name_lbl.setObjectName("MutedLabel")
        action_row.addWidget(name_lbl)

        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("Automatic safe filename")
        action_row.addWidget(self.filename_edit, 1)

        self.download_btn = QPushButton("Download")
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setIcon(make_icon("download", "#ffffff", 16))
        self.download_btn.setMinimumHeight(40)
        self.download_btn.clicked.connect(self._emit_download)
        action_row.addWidget(self.download_btn)

        root.addLayout(action_row)

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

        # Thumbnail
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
            self.sub_label.setText(f"Direct downloadable resource from {metadata.hostname}")
            self.duration_or_size_badge.setText(
                format_bytes(metadata.total_bytes) if metadata.total_bytes else "Unknown size"
            )
            self.extra_badge.setText(
                "Pause / Resume Supported" if metadata.supports_resume else "Single-stream Download"
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
                format_bytes(metadata.total_bytes) if metadata.total_bytes is not None else "Unknown (streamed)"
            )
            self._direct_fields["host"].setText(metadata.hostname)
            self._direct_fields["resume"].setText(
                "HTTP Range Supported" if metadata.supports_resume else "Not advertised by server"
            )

            self.direct_details_card.setVisible(True)
            self.media_formats_box.setVisible(False)
            self.download_btn.setText("Download File")
            self.download_btn.setEnabled(True)
        else:
            uploader_parts = [p for p in [metadata.uploader, _format_count(metadata.view_count)] if p]
            self.sub_label.setText(" · ".join(uploader_parts) if uploader_parts else metadata.hostname)
            self.duration_or_size_badge.setText(
                f"Duration: {format_duration(metadata.duration_seconds)}"
                if metadata.duration_seconds is not None
                else "Media Stream"
            )
            if metadata.is_playlist and metadata.playlist_count:
                self.extra_badge.setText(f"Playlist ({metadata.playlist_count} items · first selected)")
                self.extra_badge.setVisible(True)
            else:
                self.extra_badge.setText(f"{len(metadata.formats)} formats")
                self.extra_badge.setVisible(True)

            if metadata.description:
                snippet = " ".join(metadata.description.split())[:180]
                self.desc_label.setText(snippet)
                self.desc_label.setVisible(True)
            else:
                self.desc_label.setVisible(False)

            self.direct_details_card.setVisible(False)
            self.media_formats_box.setVisible(True)
            self.download_btn.setText("Add to Queue & Download")
            self._populate_formats()

        self.setVisible(True)

    def _set_fallback_thumb(self, engine_type: EngineType) -> None:
        icon_name = "file" if engine_type == EngineType.DIRECT_HTTP else "download"
        self.thumb_label.setPixmap(make_icon(icon_name, "#6366f1", 40).pixmap(40, 40))

    def _set_filter(self, filter_key: str) -> None:
        self._current_filter = filter_key
        self._populate_formats()

    def _populate_formats(self) -> None:
        self.format_list.clear()
        if not self._metadata:
            self.download_btn.setEnabled(False)
            return

        for fmt in self._metadata.formats:
            if self._current_filter != "all" and fmt.kind.value != self._current_filter:
                continue
            suffix = "  [FFmpeg required]" if (fmt.requires_ffmpeg and not self._ffmpeg_available) else ""
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
                "This format requires FFmpeg (missing on system). Choose a combined format or install FFmpeg."
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
