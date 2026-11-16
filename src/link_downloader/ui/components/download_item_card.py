"""Card widget displaying live progress and per-job actions for a DownloadJob."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from link_downloader.core.enums import DownloadStatus
from link_downloader.core.models import DownloadJob, format_bytes, format_duration
from link_downloader.ui.styles.theme import make_icon

_STATUS_BADGES: dict[DownloadStatus, tuple[str, str]] = {
    DownloadStatus.RESOLVING: ("Resolving", "BadgeInfo"),
    DownloadStatus.WAITING: ("Starting", "BadgeInfo"),
    DownloadStatus.QUEUED: ("Queued", "BadgeInfo"),
    DownloadStatus.DOWNLOADING: ("Downloading", "BadgeInfo"),
    DownloadStatus.PAUSED: ("Paused", "BadgeWarning"),
    DownloadStatus.PROCESSING: ("Processing", "BadgeInfo"),
    DownloadStatus.COMPLETED: ("Completed", "BadgeSuccess"),
    DownloadStatus.CANCELLED: ("Cancelled", "BadgeWarning"),
    DownloadStatus.FAILED: ("Failed", "BadgeDanger"),
}


def _format_speed(bps: float | None) -> str:
    if bps is None or bps <= 0:
        return ""
    return f"{format_bytes(bps)}/s"


class DownloadItemCard(QFrame):
    """Displays real-time telemetry and contextual Pause/Resume/Cancel/Retry/File controls."""

    pause_clicked = Signal(str)
    resume_clicked = Signal(str)
    cancel_clicked = Signal(str)
    retry_clicked = Signal(str)
    open_file_clicked = Signal(str)
    show_folder_clicked = Signal(str)

    def __init__(self, job: DownloadJob, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.job_id = job.job_id

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(6)

        # Header row (responsive: side-by-side wide, stacked narrow)
        self._header_box = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._header_box.setSpacing(8)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        self.title_label = QLabel(job.title)
        self.title_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.meta_label = QLabel(f"{job.platform} · {job.format_label}")
        self.meta_label.setObjectName("MutedLabel")
        self.meta_label.setWordWrap(True)
        self.meta_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title_col.addWidget(self.title_label)
        title_col.addWidget(self.meta_label)
        self._header_box.addLayout(title_col, 1)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        self.status_badge = QLabel("Queued")
        self.status_badge.setObjectName("BadgeInfo")
        actions_row.addWidget(self.status_badge)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setObjectName("GhostButton")
        self.pause_btn.setIcon(make_icon("pause", "#475569", 13))
        self.pause_btn.clicked.connect(lambda: self.pause_clicked.emit(self.job_id))
        actions_row.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("Resume")
        self.resume_btn.setObjectName("PrimaryButton")
        self.resume_btn.setIcon(make_icon("play", "#ffffff", 13))
        self.resume_btn.clicked.connect(lambda: self.resume_clicked.emit(self.job_id))
        actions_row.addWidget(self.resume_btn)

        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setObjectName("GhostButton")
        self.retry_btn.setIcon(make_icon("retry", "#475569", 13))
        self.retry_btn.clicked.connect(lambda: self.retry_clicked.emit(self.job_id))
        actions_row.addWidget(self.retry_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.clicked.connect(lambda: self.cancel_clicked.emit(self.job_id))
        actions_row.addWidget(self.cancel_btn)

        self.open_btn = QPushButton("Open")
        self.open_btn.setObjectName("PrimaryButton")
        self.open_btn.clicked.connect(self._emit_open_file)
        actions_row.addWidget(self.open_btn)

        self.folder_btn = QPushButton("Folder")
        self.folder_btn.setObjectName("GhostButton")
        self.folder_btn.setIcon(make_icon("folder", "#475569", 13))
        self.folder_btn.setToolTip("Show file in folder")
        self.folder_btn.clicked.connect(self._emit_show_folder)
        actions_row.addWidget(self.folder_btn)
        actions_row.addStretch(0)

        self._header_box.addLayout(actions_row)
        root.addLayout(self._header_box)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        root.addWidget(self.progress_bar)

        # Telemetry row
        bottom = QHBoxLayout()
        self.telemetry_label = QLabel("Queued")
        self.telemetry_label.setObjectName("MutedLabel")
        self.telemetry_label.setWordWrap(True)
        self.telemetry_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("MutedLabel")
        bottom.addWidget(self.telemetry_label, 1)
        bottom.addWidget(self.percent_label)
        root.addLayout(bottom)

        self._file_path_str: str = ""
        self.update_from_job(job)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        direction = (
            QBoxLayout.Direction.TopToBottom
            if event.size().width() < 520
            else QBoxLayout.Direction.LeftToRight
        )
        if self._header_box.direction() != direction:
            self._header_box.setDirection(direction)

    def _emit_open_file(self) -> None:
        if self._file_path_str:
            self.open_file_clicked.emit(self._file_path_str)

    def _emit_show_folder(self) -> None:
        if self._file_path_str:
            self.show_folder_clicked.emit(self._file_path_str)

    def update_from_job(self, job: DownloadJob) -> None:
        self.title_label.setText(job.title)
        prog = job.progress
        dest_name = prog.filename if prog and prog.filename else (
            job.reserved_path.name if job.reserved_path else job.title
        )
        self.meta_label.setText(f"{job.platform} · {dest_name}")
        self._file_path_str = str(
            job.final_path
            or (prog.destination_path if prog and prog.destination_path else "")
            or (job.reserved_path or "")
        )

        badge_text, badge_obj = _STATUS_BADGES.get(job.status, (job.status.value.title(), "BadgeInfo"))
        self.status_badge.setText(badge_text)
        self.status_badge.setObjectName(badge_obj)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

        # Update progress bar
        if job.status == DownloadStatus.COMPLETED:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.percent_label.setText("100%")
        elif job.status == DownloadStatus.PROCESSING or (
            job.status == DownloadStatus.DOWNLOADING and (prog is None or prog.percent is None)
        ):
            self.progress_bar.setRange(0, 0)
            self.percent_label.setText("Streaming...")
        elif prog and prog.percent is not None:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(max(0, min(100, round(prog.percent))))
            self.percent_label.setText(f"{prog.percent:.1f}%")
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.percent_label.setText("—")

        # Update telemetry text
        if job.status == DownloadStatus.FAILED and job.error_message:
            self.telemetry_label.setText(job.error_message)
            self.telemetry_label.setObjectName("ErrorLabel")
        else:
            self.telemetry_label.setObjectName("MutedLabel")
            parts: list[str] = []
            if prog and prog.downloaded_bytes > 0:
                if prog.total_bytes:
                    parts.append(f"{format_bytes(prog.downloaded_bytes)} / {format_bytes(prog.total_bytes)}")
                else:
                    parts.append(f"{format_bytes(prog.downloaded_bytes)} downloaded")
            if prog and prog.speed_bps and job.status == DownloadStatus.DOWNLOADING:
                parts.append(_format_speed(prog.speed_bps))
            if prog and prog.eta_seconds is not None and job.status == DownloadStatus.DOWNLOADING:
                parts.append(f"ETA {format_duration(prog.eta_seconds)}")
            if job.status == DownloadStatus.COMPLETED and self._file_path_str:
                parts.append(self._file_path_str)
            elif not parts and prog and prog.message:
                parts.append(prog.message)
            self.telemetry_label.setText(" · ".join(parts) if parts else badge_text)

        self.telemetry_label.style().unpolish(self.telemetry_label)
        self.telemetry_label.style().polish(self.telemetry_label)

        # Contextual button visibility (Pause only exposed when supported!)
        is_downloading = job.status == DownloadStatus.DOWNLOADING
        is_paused = job.status == DownloadStatus.PAUSED
        is_cancellable = job.status in {
            DownloadStatus.QUEUED,
            DownloadStatus.WAITING,
            DownloadStatus.RESOLVING,
            DownloadStatus.DOWNLOADING,
            DownloadStatus.PAUSED,
            DownloadStatus.PROCESSING,
        }
        is_retryable = job.status in {DownloadStatus.FAILED, DownloadStatus.CANCELLED}
        is_completed = job.status == DownloadStatus.COMPLETED

        self.pause_btn.setVisible(is_downloading and job.can_pause)
        self.resume_btn.setVisible(is_paused and job.can_resume)
        self.cancel_btn.setVisible(is_cancellable)
        self.retry_btn.setVisible(is_retryable)
        self.open_btn.setVisible(is_completed)
        self.folder_btn.setVisible(is_completed)
