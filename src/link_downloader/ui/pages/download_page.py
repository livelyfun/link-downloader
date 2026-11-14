"""Primary Download dashboard page: URL analysis, metadata preview, and active jobs."""

from __future__ import annotations

from PySide6.QtCore import Signal
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

from link_downloader.core.enums import EngineType, OverwriteBehavior, ResourceKind
from link_downloader.core.models import (
    DownloadJob,
    DownloadRequest,
    FormatOption,
    ResourceMetadata,
)
from link_downloader.platform.file_actions import open_file, reveal_in_file_manager
from link_downloader.services.download_manager import DownloadManager
from link_downloader.ui.components.download_item_card import DownloadItemCard
from link_downloader.ui.components.empty_state import EmptyStateWidget
from link_downloader.ui.components.metadata_preview_card import MetadataPreviewCard
from link_downloader.ui.components.url_input_card import UrlInputCard


class DownloadPage(QWidget):
    """Dashboard page for pasting/dropping URLs, previewing metadata, and starting downloads."""

    open_queue_requested = Signal()

    def __init__(self, manager: DownloadManager, *, allow_private: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._active_request_id: str | None = None
        self._job_cards: dict[str, DownloadItemCard] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("ScrollContent")
        scroll.setWidget(content)

        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(24, 22, 24, 24)
        self._layout.setSpacing(16)

        title_row = QHBoxLayout()
        page_title = QLabel("Download")
        page_title.setObjectName("PageTitle")
        title_row.addWidget(page_title)
        title_row.addStretch()
        self._dest_hint = QLabel(f"Saving to: {self._manager.settings.download_folder}")
        self._dest_hint.setObjectName("MutedLabel")
        title_row.addWidget(self._dest_hint)
        self._layout.addLayout(title_row)

        self.url_card = UrlInputCard(allow_private=allow_private)
        self.url_card.analyze_requested.connect(self._on_analyze_requested)
        self.url_card.cleared.connect(self._on_cleared)
        self._layout.addWidget(self.url_card)

        # Analyzing progress indicator
        self.loading_card = QFrame()
        self.loading_card.setObjectName("Card")
        self.loading_card.setVisible(False)
        load_layout = QVBoxLayout(self.loading_card)
        load_layout.setContentsMargins(18, 16, 18, 16)
        load_layout.setSpacing(8)
        load_lbl = QLabel("Resolving URL capabilities and inspecting available streams or headers...")
        load_lbl.setObjectName("MutedLabel")
        load_bar = QProgressBar()
        load_bar.setRange(0, 0)
        load_layout.addWidget(load_lbl)
        load_layout.addWidget(load_bar)
        self._layout.addWidget(self.loading_card)

        # Preview card
        self.preview_card = MetadataPreviewCard()
        self.preview_card.download_requested.connect(self._on_download_requested)
        self._layout.addWidget(self.preview_card)

        # Empty state when nothing analyzed yet
        self.idle_empty_state = EmptyStateWidget(
            "Ready to Download",
            "Paste a YouTube, Vimeo, SoundCloud, or media page link to inspect formats, "
            "or enter a direct file URL (.mp4, .mp3, .pdf, .zip, images, packages).",
            icon_name="link",
        )
        self._layout.addWidget(self.idle_empty_state)

        # Active & recent jobs section
        jobs_header = QHBoxLayout()
        self.jobs_section_label = QLabel("RECENT ACTIVITY")
        self.jobs_section_label.setObjectName("SectionTitle")
        jobs_header.addWidget(self.jobs_section_label)
        jobs_header.addStretch()

        self.view_queue_btn = QPushButton("Open Full Queue")
        self.view_queue_btn.setObjectName("GhostButton")
        self.view_queue_btn.clicked.connect(self.open_queue_requested.emit)
        jobs_header.addWidget(self.view_queue_btn)

        self.jobs_header_widget = QWidget()
        self.jobs_header_widget.setLayout(jobs_header)
        self.jobs_header_widget.setVisible(False)
        self._layout.addWidget(self.jobs_header_widget)

        self.jobs_container = QVBoxLayout()
        self.jobs_container.setSpacing(10)
        self._layout.addLayout(self.jobs_container)
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
        self._dest_hint.setText(f"Saving to: {settings.download_folder}")

    def _on_analyze_requested(self, normalized_url: str) -> None:
        self.url_card.set_loading(True)
        self.preview_card.setVisible(False)
        self.idle_empty_state.setVisible(False)
        self.loading_card.setVisible(True)
        self._active_request_id = self._manager.analyze_url(normalized_url)

    def _on_cleared(self) -> None:
        self._active_request_id = None
        self.loading_card.setVisible(False)
        self.preview_card.setVisible(False)
        self.idle_empty_state.setVisible(True)

    def _on_metadata_resolved(
        self,
        request_id: str,
        metadata: ResourceMetadata,
        thumb_bytes: bytes | None,
    ) -> None:
        if request_id != self._active_request_id:
            return
        self.url_card.set_loading(False)
        self.loading_card.setVisible(False)

        if metadata.engine_type == EngineType.DIRECT_HTTP:
            badge_text = "Direct File Download · HTTP/HTTPS"
        elif metadata.resource_kind == ResourceKind.GENERIC_MEDIA_PAGE:
            badge_text = "Webpage Media Extraction · yt-dlp"
        else:
            badge_text = f"Media Platform · {metadata.source_platform}"

        self.url_card.set_detected_engine(metadata.engine_type, badge_text)
        deps = self._manager.check_dependencies()
        ffmpeg_ok = any(d.name == "FFmpeg" and d.available for d in deps)
        self.preview_card.set_metadata(metadata, thumb_bytes, ffmpeg_available=ffmpeg_ok)

    def _on_metadata_failed(self, request_id: str, error_msg: str) -> None:
        if request_id != self._active_request_id:
            return
        self.url_card.set_loading(False)
        self.loading_card.setVisible(False)
        self.preview_card.setVisible(False)
        self.idle_empty_state.setVisible(True)
        self.url_card.set_error(error_msg)

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
        self.jobs_header_widget.setVisible(bool(self._job_cards))

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
        self.jobs_container.insertWidget(0, card)
        self.jobs_header_widget.setVisible(True)
        # Keep Download page quick-activity view concise (max 4 recent cards; full list in Queue page)
        while self.jobs_container.count() > 4:
            last_item = self.jobs_container.takeAt(self.jobs_container.count() - 1)
            w = last_item.widget()
            if isinstance(w, DownloadItemCard):
                self._job_cards.pop(w.job_id, None)
                w.deleteLater()
