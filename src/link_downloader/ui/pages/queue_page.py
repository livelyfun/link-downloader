"""Download Queue page managing multiple concurrent, paused, and queued jobs."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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


class QueuePage(QWidget):
    """Displays all queued, active, paused, completed, failed, and cancelled downloads."""

    def __init__(self, manager: DownloadManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._cards: dict[str, DownloadItemCard] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        # Header + controls
        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("Download Queue")
        title.setObjectName("PageTitle")
        header.addWidget(title)

        self.summary_label = QLabel("0 items")
        self.summary_label.setObjectName("MutedLabel")
        header.addWidget(self.summary_label)
        header.addStretch()

        conc_lbl = QLabel("Max concurrent:")
        conc_lbl.setObjectName("MutedLabel")
        header.addWidget(conc_lbl)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(MIN_CONCURRENT_DOWNLOADS, MAX_CONCURRENT_DOWNLOADS)
        self.concurrency_spin.setValue(self._manager.settings.concurrent_downloads)
        self.concurrency_spin.setToolTip("Maximum simultaneous downloads")
        self.concurrency_spin.valueChanged.connect(self._on_concurrency_changed)
        header.addWidget(self.concurrency_spin)

        self.retry_failed_btn = QPushButton("Retry Failed")
        self.retry_failed_btn.setObjectName("GhostButton")
        self.retry_failed_btn.clicked.connect(self._manager.retry_all_failed)
        header.addWidget(self.retry_failed_btn)

        self.clear_finished_btn = QPushButton("Remove Finished")
        self.clear_finished_btn.setObjectName("GhostButton")
        self.clear_finished_btn.clicked.connect(self._manager.remove_completed)
        header.addWidget(self.clear_finished_btn)

        self.cancel_all_btn = QPushButton("Cancel All")
        self.cancel_all_btn.setObjectName("DangerButton")
        self.cancel_all_btn.clicked.connect(self._manager.cancel_all)
        header.addWidget(self.cancel_all_btn)

        root.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("ScrollContent")
        scroll.setWidget(content)

        self._list_layout = QVBoxLayout(content)
        self._list_layout.setContentsMargins(0, 0, 6, 0)
        self._list_layout.setSpacing(10)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.empty_state = EmptyStateWidget(
            "Download Queue is Empty",
            "Analyzed URLs added to your queue will appear here with live progress, speed, ETA, and per-job controls.",
            icon_name="queue",
        )
        self._list_layout.addWidget(self.empty_state)

        self._manager.signals.job_added.connect(self._on_job_added)
        self._manager.signals.job_updated.connect(self._on_job_updated)
        self._manager.signals.queue_changed.connect(self.refresh)
        self._manager.signals.settings_changed.connect(self._on_settings_changed)
        self.refresh()

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
        self._list_layout.insertWidget(0, card)
        self.empty_state.setVisible(False)

    def refresh(self) -> None:
        jobs = self._manager.list_jobs()
        current_ids = {j.job_id for j in jobs}
        for stale_id in list(self._cards.keys()):
            if stale_id not in current_ids:
                card = self._cards.pop(stale_id)
                self._list_layout.removeWidget(card)
                card.deleteLater()

        for job in jobs:
            self._create_or_update_card(job)

        self.empty_state.setVisible(len(jobs) == 0)
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
