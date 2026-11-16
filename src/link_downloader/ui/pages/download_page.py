"""Primary Download workspace: desktop toolbar, URL command deck, inspector, and live transfers."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from link_downloader.core.enums import EngineType, FormatKind, OverwriteBehavior, ResourceKind
from link_downloader.core.models import (
    DownloadJob,
    DownloadRequest,
    FormatOption,
    ResourceMetadata,
)
from link_downloader.platform.file_actions import open_file, open_folder, reveal_in_file_manager
from link_downloader.services.download_manager import DownloadManager
from link_downloader.ui.components.download_item_card import DownloadItemCard
from link_downloader.ui.components.empty_state import EmptyStateWidget
from link_downloader.ui.components.metadata_preview_card import MetadataPreviewCard
from link_downloader.ui.components.pagination_bar import PaginationBar
from link_downloader.ui.components.url_input_card import UrlInputCard
from link_downloader.ui.styles.theme import make_icon


def _select_preset_format(metadata: ResourceMetadata, preset: str) -> FormatOption | None:
    if not metadata.formats:
        return None
    if metadata.engine_type == EngineType.DIRECT_HTTP:
        return metadata.formats[0]

    if preset == "audio":
        audio_fmts = [f for f in metadata.formats if f.kind == FormatKind.AUDIO_ONLY]
        return audio_fmts[0] if audio_fmts else metadata.formats[0]

    height_caps = {"1080p": 1080, "720p": 720, "480p": 480}
    cap = height_caps.get(preset)
    if cap is not None:
        capped = [
            f
            for f in metadata.formats
            if f.kind != FormatKind.AUDIO_ONLY and (f.height is None or f.height <= cap)
        ]
        if capped:
            return capped[0]
    return metadata.formats[0]


class DownloadPage(QWidget):
    """Desktop download workspace with quick capture, inspector, and active transfers."""

    open_queue_requested = Signal()

    def __init__(self, manager: DownloadManager, *, allow_private: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._active_request_id: str | None = None
        self._quick_presets: dict[str, str] = {}
        self._job_cards: dict[str, DownloadItemCard] = {}
        self._job_order: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Native desktop top window toolbar
        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(20, 10, 20, 10)
        tb_lay.setSpacing(10)

        page_title = QLabel("Downloads")
        page_title.setObjectName("PageTitle")
        tb_lay.addWidget(page_title)
        tb_lay.addStretch()

        self._dest_hint = QLabel(self._manager.settings.download_folder)
        self._dest_hint.setObjectName("MutedLabel")
        self._dest_hint.setToolTip(self._manager.settings.download_folder)
        self._dest_hint.setMaximumWidth(280)
        tb_lay.addWidget(self._dest_hint)

        self.open_dest_btn = QPushButton("Open Folder")
        self.open_dest_btn.setObjectName("GhostButton")
        self.open_dest_btn.setIcon(make_icon("folder", "#475569", 14))
        self.open_dest_btn.clicked.connect(
            lambda: open_folder(self._manager.settings.download_folder)
        )
        tb_lay.addWidget(self.open_dest_btn)
        outer.addWidget(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("ScrollContent")
        scroll.setWidget(content)

        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(20, 16, 20, 20)
        self._layout.setSpacing(12)

        self.url_card = UrlInputCard(allow_private=allow_private)
        self.url_card.analyze_requested.connect(self._on_analyze_requested)
        self.url_card.quick_download_requested.connect(self._on_quick_download_requested)
        self.url_card.cleared.connect(self._on_cleared)
        self._layout.addWidget(self.url_card)

        # Analyzing progress indicator
        self.loading_card = QFrame()
        self.loading_card.setObjectName("Card")
        self.loading_card.setVisible(False)
        load_layout = QVBoxLayout(self.loading_card)
        load_layout.setContentsMargins(14, 12, 14, 12)
        load_layout.setSpacing(6)
        load_lbl = QLabel("Inspecting link and resolving downloadable streams...")
        load_lbl.setObjectName("MutedLabel")
        load_bar = QProgressBar()
        load_bar.setRange(0, 0)
        load_layout.addWidget(load_lbl)
        load_layout.addWidget(load_bar)
        self._layout.addWidget(self.loading_card)

        # Two-column Media Inspector card
        self.preview_card = MetadataPreviewCard()
        self.preview_card.download_requested.connect(self._on_download_requested)
        self.preview_card.closed.connect(self._on_preview_closed)
        self._layout.addWidget(self.preview_card)

        # Active & Recent Transfers section (always visible as core desktop workspace)
        jobs_header = QHBoxLayout()
        jobs_header.setSpacing(8)
        self.jobs_section_label = QLabel("ACTIVE & RECENT TRANSFERS")
        self.jobs_section_label.setObjectName("SectionTitle")
        jobs_header.addWidget(self.jobs_section_label)
        jobs_header.addStretch()

        self.view_queue_btn = QPushButton("Full Queue")
        self.view_queue_btn.setObjectName("GhostButton")
        self.view_queue_btn.clicked.connect(self.open_queue_requested.emit)
        jobs_header.addWidget(self.view_queue_btn)

        self.jobs_header_widget = QWidget()
        self.jobs_header_widget.setLayout(jobs_header)
        self._layout.addWidget(self.jobs_header_widget)

        self.jobs_container = QVBoxLayout()
        self.jobs_container.setSpacing(8)
        self._layout.addLayout(self.jobs_container)

        self.pagination_bar = PaginationBar(
            default_page_size=5,
            page_size_options=(5, 10, 20),
        )
        self.pagination_bar.page_changed.connect(lambda _p: self._apply_jobs_pagination())
        self.pagination_bar.page_size_changed.connect(lambda _s: self._apply_jobs_pagination())
        self._layout.addWidget(self.pagination_bar)

        self.idle_empty_state = EmptyStateWidget(
            "No active transfers",
            "Paste or drop a link above — click Quick Download for instant capture or Inspect Formats to pick a stream.",
            icon_name="download",
        )
        self._layout.addWidget(self.idle_empty_state)
        self._layout.addStretch()

        # Connect manager signals
        self._manager.signals.metadata_resolved.connect(self._on_metadata_resolved)
        self._manager.signals.metadata_failed.connect(self._on_metadata_failed)
        self._manager.signals.job_added.connect(self._on_job_added)
        self._manager.signals.job_updated.connect(self._on_job_updated)
        self._manager.signals.queue_changed.connect(self._sync_jobs)
        self._manager.signals.settings_changed.connect(self._on_settings_changed)

    def analyze_external_url(self, url: str) -> None:
        """Populate URL field and trigger analysis immediately (used by History 'Download Again')."""
        self.url_card.set_url(url)
        self._on_analyze_requested(url)

    def _on_settings_changed(self, settings) -> None:
        self._dest_hint.setText(settings.download_folder)

    def _on_analyze_requested(self, normalized_url: str) -> None:
        self.url_card.set_loading(True)
        self.preview_card.setVisible(False)
        self.loading_card.setVisible(True)
        self._active_request_id = self._manager.analyze_url(normalized_url)

    def _on_quick_download_requested(self, normalized_url: str, preset: str) -> None:
        self.url_card.set_loading(True)
        self.preview_card.setVisible(False)
        self.loading_card.setVisible(True)
        req_id = self._manager.analyze_url(normalized_url)
        self._active_request_id = req_id
        self._quick_presets[req_id] = preset

    def _on_cleared(self) -> None:
        self._active_request_id = None
        self.loading_card.setVisible(False)
        self.preview_card.setVisible(False)
        self._update_empty_transfer_visibility()

    def _on_preview_closed(self) -> None:
        self._update_empty_transfer_visibility()

    def _on_metadata_resolved(
        self,
        request_id: str,
        metadata: ResourceMetadata,
        thumb_bytes: bytes | None,
    ) -> None:
        if request_id != self._active_request_id:
            self._quick_presets.pop(request_id, None)
            return
        self.url_card.set_loading(False)
        self.loading_card.setVisible(False)

        if metadata.engine_type == EngineType.DIRECT_HTTP:
            badge_text = "Direct HTTP"
        elif metadata.resource_kind == ResourceKind.GENERIC_MEDIA_PAGE:
            badge_text = "Web Media"
        else:
            badge_text = metadata.source_platform

        self.url_card.set_detected_engine(metadata.engine_type, badge_text)
        deps = self._manager.check_dependencies()
        ffmpeg_ok = any(d.name == "FFmpeg" and d.available for d in deps)
        self.preview_card.set_metadata(metadata, thumb_bytes, ffmpeg_available=ffmpeg_ok)

        quick_preset = self._quick_presets.pop(request_id, None)
        if quick_preset is not None:
            fmt = _select_preset_format(metadata, quick_preset)
            if fmt is not None:
                self._on_download_requested(metadata, fmt, "")

    def _on_metadata_failed(self, request_id: str, error_msg: str) -> None:
        self._quick_presets.pop(request_id, None)
        if request_id != self._active_request_id:
            return
        self.url_card.set_loading(False)
        self.loading_card.setVisible(False)
        self.preview_card.setVisible(False)
        self.url_card.set_error(error_msg)
        self._update_empty_transfer_visibility()

    def _on_download_requested(
        self,
        metadata: ResourceMetadata,
        fmt: FormatOption,
        custom_filename: str,
    ) -> None:
        settings = self._manager.settings
        request = DownloadRequest(
            url=metadata.normalized_url or metadata.url,
            destination_dir=settings.download_path,
            selected_format=fmt,
            preferred_filename=custom_filename or None,
            auto_convert_mp3=bool(settings.auto_convert_mp3 or fmt.convert_to_mp3),
            overwrite_behavior=OverwriteBehavior(settings.overwrite_behavior),
            metadata=metadata,
            prefer_ipv4=settings.prefer_ipv4,
        )
        self._manager.enqueue_download(request)

    def _on_job_added(self, job: DownloadJob) -> None:
        self._ensure_job_card(job)

    def _on_job_updated(self, job: DownloadJob) -> None:
        card = self._job_cards.get(job.job_id)
        if card is not None:
            card.update_from_job(job)

    def _sync_jobs(self) -> None:
        jobs = self._manager.list_jobs()
        current_ids = {j.job_id for j in jobs}
        for stale_id in list(self._job_cards.keys()):
            if stale_id not in current_ids:
                card = self._job_cards.pop(stale_id)
                self.jobs_container.removeWidget(card)
                card.deleteLater()
        self._job_order = [jid for jid in self._job_order if jid in current_ids]
        self._update_empty_transfer_visibility()
        self._apply_jobs_pagination()

    def _update_empty_transfer_visibility(self) -> None:
        self.idle_empty_state.setVisible(len(self._job_cards) == 0)

    def _apply_jobs_pagination(self) -> None:
        self.pagination_bar.set_total_items(len(self._job_order))
        start, end = self.pagination_bar.current_range(len(self._job_order))
        visible_ids = set(self._job_order[start:end])
        for jid, card in self._job_cards.items():
            card.setVisible(jid in visible_ids)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._dest_hint.setVisible(event.size().width() >= 560)

    def _ensure_job_card(self, job: DownloadJob) -> None:
        if job.job_id in self._job_cards:
            self._job_cards[job.job_id].update_from_job(job)
            return
        card = DownloadItemCard(job)
        card.pause_clicked.connect(self._manager.pause_job)
        card.resume_clicked.connect(self._manager.resume_job)
        card.cancel_clicked.connect(self._manager.cancel_job)
        card.retry_clicked.connect(self._manager.retry_job)
        card.open_file_clicked.connect(open_file)
        card.show_folder_clicked.connect(
            lambda fp: reveal_in_file_manager(fp, self._manager.settings.download_folder)
        )
        self._job_cards[job.job_id] = card
        self._job_order.insert(0, job.job_id)
        self.jobs_container.insertWidget(0, card)
        self._update_empty_transfer_visibility()
        self._apply_jobs_pagination()
