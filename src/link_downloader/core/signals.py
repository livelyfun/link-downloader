"""Qt signal containers for background workers and queue state updates."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class MetadataWorkerSignals(QObject):
    """Signals emitted by MetadataWorker on completion or failure."""

    finished = Signal(str, object, object)  # request_id, ResourceMetadata, thumbnail_bytes | None
    error = Signal(str, str)  # request_id, error_message


class DownloadWorkerSignals(QObject):
    """Signals emitted by DownloadWorker during job execution."""

    progress = Signal(object)  # DownloadProgress
    status_changed = Signal(str, str)  # job_id, DownloadStatus.value
    completed = Signal(str, str, int)  # job_id, final_path_str, file_size
    paused = Signal(str)  # job_id
    cancelled = Signal(str)  # job_id
    failed = Signal(str, str)  # job_id, error_message


class FfmpegWorkerSignals(QObject):
    """Signals emitted during one-click background FFmpeg installation."""

    progress = Signal(int, str)  # percent (0..100), status_message
    finished = Signal(str)  # installed ffmpeg binary path
    failed = Signal(str)  # user-friendly error message


class ManagerSignals(QObject):
    """Application-level signals emitted by DownloadManager to UI pages."""

    metadata_resolved = Signal(str, object, object)  # request_id, ResourceMetadata, bytes | None
    metadata_failed = Signal(str, str)  # request_id, error_message
    job_added = Signal(object)  # DownloadJob
    job_updated = Signal(object)  # DownloadJob
    queue_changed = Signal()
    history_updated = Signal()
    settings_changed = Signal(object)  # AppSettings
    ffmpeg_install_started = Signal()
    ffmpeg_install_progress = Signal(int, str)
    ffmpeg_install_finished = Signal(str)
    ffmpeg_install_failed = Signal(str)
    dependencies_changed = Signal()
