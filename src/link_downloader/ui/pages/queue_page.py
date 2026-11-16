"""Responsive Download Queue page managing concurrent, paused, queued, and paginated jobs."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from link_downloader.config.defaults import MAX_CONCURRENT_DOWNLOADS, MIN_CONCURRENT_DOWNLOADS
from link_downloader.core.models import DownloadJob
from link_downloader.platform.file_actions import open_file, reveal_in_file_manager
from link_downloader.services.download_manager import DownloadManager
from link_downloader.ui.components.download_item_card import DownloadItemCard
from link_downloader.ui.components.empty_state import EmptyStateWidget
from link_downloader.ui.components.pagination_bar import PaginationBar


class QueuePage(QWidget):
    """Displays queued, active, paused, completed, failed, and cancelled downloads with pagination."""

    def __init__(self, manager: DownloadManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._cards: dict[str, DownloadItemCard] = {}
        self._job_order: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Responsive desktop toolbar
        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        self._toolbar_box = QBoxLayout(QBoxLayout.Direction.LeftToRight, toolbar)
        self._toolbar_box.setContentsMargins(20, 10, 20, 10)
        self._toolbar_box.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("Queue")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)

        self.summary_label = QLabel("0 items")
        self.summary_label.setObjectName("MutedLabel")
        title_row.addWidget(self.summary_label)
        title_row.addStretch()
        self._toolbar_box.addLayout(title_row, 1)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(6)
        conc_lbl = QLabel("Concurrent:")
        conc_lbl.setObjectName("MutedLabel")
        controls_row.addWidget(conc_lbl)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(MIN_CONCURRENT_DOWNLOADS, MAX_CONCURRENT_DOWNLOADS)
        self.concurrency_spin.setValue(self._manager.settings.concurrent_downloads)
        self.concurrency_spin.setToolTip("Maximum simultaneous downloads")
        self.concurrency_spin.valueChanged.connect(self._on_concurrency_changed)
        controls_row.addWidget(self.concurrency_spin)

        self.retry_failed_btn = QPushButton("Retry Failed")
        self.retry_failed_btn.setObjectName("GhostButton")
        self.retry_failed_btn.clicked.connect(self._manager.retry_all_failed)
        controls_row.addWidget(self.retry_failed_btn)

        self.clear_finished_btn = QPushButton("Clear Finished")
        self.clear_finished_btn.setObjectName("GhostButton")
        self.clear_finished_btn.clicked.connect(self._manager.remove_completed)
        controls_row.addWidget(self.clear_finished_btn)

        self.cancel_all_btn = QPushButton("Cancel All")
        self.cancel_all_btn.setObjectName("DangerButton")
        self.cancel_all_btn.clicked.connect(self._manager.cancel_all)
        controls_row.addWidget(self.cancel_all_btn)
        controls_row.addStretch(0)
        self._toolbar_box.addLayout(controls_row)

        root.addWidget(toolbar)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 14, 20, 14)
        body_lay.setSpacing(10)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body_lay.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("ScrollContent")
        scroll.setWidget(content)

        self._list_layout = QVBoxLayout(content)
        self._list_layout.setContentsMargins(0, 0, 6, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.empty_state = EmptyStateWidget(
            "Download Queue is Empty",
            "Analyzed URLs added to your queue will appear here with live progress, speed, ETA, and per-job controls.",
            icon_name="queue",
        )
        self._list_layout.addWidget(self.empty_state)

        self.pagination_bar = PaginationBar(
            default_page_size=10,
            page_size_options=(5, 10, 25, 50),
        )
        self.pagination_bar.page_changed.connect(lambda _p: self._apply_pagination())
        self.pagination_bar.page_size_changed.connect(lambda _s: self._apply_pagination())
        body_lay.addWidget(self.pagination_bar)

        root.addWidget(body, 1)

        self._manager.signals.job_added.connect(self._on_job_added)
        self._manager.signals.job_updated.connect(self._on_job_updated)
        self._manager.signals.queue_changed.connect(self.refresh)
        self._manager.signals.settings_changed.connect(self._on_settings_changed)
        self.refresh()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        direction = (
            QBoxLayout.Direction.TopToBottom
            if event.size().width() < 680
            else QBoxLayout.Direction.LeftToRight
        )
        if self._toolbar_box.direction() != direction:
            self._toolbar_box.setDirection(direction)

    def _on_settings_changed(self, settings) -> None:
        if self.concurrency_spin.value() != settings.concurrent_downloads:
            self.concurrency_spin.blockSignals(True)
            self.concurrency_spin.setValue(settings.concurrent_downloads)
            self.concurrency_spin.blockSignals(False)

    def _on_concurrency_changed(self, value: int) -> None:
        updated = replace(self._manager.settings, concurrent_downloads=value)
        self._manager.update_settings(updated)

    def _on_job_added(self, job: DownloadJob) -> None:
        self._create_or_update_card(job)
        self._apply_pagination()
        self._update_summary()

    def _on_job_updated(self, job: DownloadJob) -> None:
        if job.job_id in self._cards:
            self._cards[job.job_id].update_from_job(job)
        self._update_summary()

    def _create_or_update_card(self, job: DownloadJob) -> None:
        if job.job_id in self._cards:
            self._cards[job.job_id].update_from_job(job)
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
        self._cards[job.job_id] = card
        self._job_order.insert(0, job.job_id)
        self._list_layout.insertWidget(0, card)
        self.empty_state.setVisible(False)

    def _apply_pagination(self) -> None:
        self.pagination_bar.set_total_items(len(self._job_order))
        start, end = self.pagination_bar.current_range(len(self._job_order))
        visible_ids = set(self._job_order[start:end])
        for jid, card in self._cards.items():
            card.setVisible(jid in visible_ids)

    def refresh(self) -> None:
        jobs = self._manager.list_jobs()
        current_ids = {j.job_id for j in jobs}
        for stale_id in list(self._cards.keys()):
            if stale_id not in current_ids:
                card = self._cards.pop(stale_id)
                self._list_layout.removeWidget(card)
                card.deleteLater()
        self._job_order = [jid for jid in self._job_order if jid in current_ids]

        for job in jobs:
            self._create_or_update_card(job)

        self.empty_state.setVisible(len(jobs) == 0)
        self._apply_pagination()
        self._update_summary()

    def _update_summary(self) -> None:
        jobs = self._manager.list_jobs()
        active = sum(1 for j in jobs if j.status.is_active)
        queued = sum(1 for j in jobs if j.status.value in ("queued", "waiting"))
        self.summary_label.setText(f"{len(jobs)} total · {active} active · {queued} waiting")
        self.cancel_all_btn.setEnabled(any(not j.status.is_terminal for j in jobs))
        self.clear_finished_btn.setEnabled(any(j.status.is_terminal for j in jobs))
        self.retry_failed_btn.setEnabled(
            any(j.status.value in ("failed", "cancelled") for j in jobs)
        )
