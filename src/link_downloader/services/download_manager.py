"""Application service coordinating metadata probing, queue scheduling, workers, and history."""

from __future__ import annotations

import contextlib
import logging
import threading
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool

from link_downloader.config.defaults import AppSettings
from link_downloader.config.settings import SettingsManager
from link_downloader.core.enums import DownloadStatus, EngineType
from link_downloader.core.models import (
    DependencyStatus,
    DownloadJob,
    DownloadProgress,
    DownloadRequest,
    HistoryEntry,
    MigrationReport,
    ResourceMetadata,
    utc_now_iso,
)
from link_downloader.core.signals import ManagerSignals
from link_downloader.database.connection import DatabaseConnection
from link_downloader.database.repository import HistoryRepository
from link_downloader.engines.direct_http_engine import DirectHttpEngine
from link_downloader.engines.resolver import UrlCapabilityResolver
from link_downloader.engines.ytdlp_engine import YtDlpEngine
from link_downloader.services.dependency_service import DependencyService
from link_downloader.services.ffmpeg_service import FfmpegService
from link_downloader.services.metadata_service import MetadataService
from link_downloader.services.migration_service import LegacyMigrationService
from link_downloader.services.queue_service import QueueService
from link_downloader.workers.download_worker import DownloadWorker
from link_downloader.workers.ffmpeg_worker import FfmpegInstallWorker
from link_downloader.workers.metadata_worker import MetadataWorker

logger = logging.getLogger(__name__)


class DownloadManager(QObject):
    """Orchestrates background URL analysis, bounded concurrent downloads, and SQLite history."""

    def __init__(
        self,
        *,
        settings_manager: SettingsManager | None = None,
        history_repo: HistoryRepository | None = None,
        ffmpeg_service: FfmpegService | None = None,
        dependency_service: DependencyService | None = None,
        allow_private: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.signals = ManagerSignals(self)

        self._settings_manager = settings_manager or SettingsManager()
        self._history_repo = history_repo or HistoryRepository(DatabaseConnection())
        self._ffmpeg = ffmpeg_service or FfmpegService()
        self._dependency_service = dependency_service or DependencyService(self._ffmpeg)
        self._allow_private = allow_private

        self._migration_report = MigrationReport()
        self._settings = self._settings_manager.load()

        self._ytdlp_engine = YtDlpEngine(
            ffmpeg_service=self._ffmpeg,
            dependency_service=self._dependency_service,
            allow_private=self._allow_private,
            prefer_ipv4=self._settings.prefer_ipv4,
        )
        self._direct_engine = DirectHttpEngine(
            allow_private=self._allow_private,
            prefer_ipv4=self._settings.prefer_ipv4,
        )
        self._resolver = UrlCapabilityResolver(
            ytdlp_engine=self._ytdlp_engine,
            direct_engine=self._direct_engine,
            allow_private=self._allow_private,
        )
        self._metadata_service = MetadataService(
            self._resolver,
            allow_private=self._allow_private,
            prefer_ipv4=self._settings.prefer_ipv4,
        )
        self._queue = QueueService(max_concurrency=self._settings.concurrent_downloads)

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(8)

        self._lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._pause_events: dict[str, threading.Event] = {}
        self._active_workers: dict[str, object] = {}
        self._shutting_down = False
        self._installing_ffmpeg = False
        self._ffmpeg_cancel_event: threading.Event | None = None

    def startup(self) -> MigrationReport:
        """Run legacy migration if needed and ensure settings and folders are initialized."""
        migration = LegacyMigrationService(self._settings_manager, self._history_repo)
        self._migration_report = migration.migrate_if_needed()
        self._settings = self._settings_manager.load()
        if not self._settings_manager.exists():
            self._settings = self._settings_manager.save(self._settings)
        self._settings_manager.ensure_download_folder(self._settings)
        self._queue.set_max_concurrency(self._settings.concurrent_downloads)
        self._rebuild_engines()
        return self._migration_report

    def _rebuild_engines(self) -> None:
        self._ytdlp_engine = YtDlpEngine(
            ffmpeg_service=self._ffmpeg,
            dependency_service=self._dependency_service,
            allow_private=self._allow_private,
            prefer_ipv4=self._settings.prefer_ipv4,
        )
        self._direct_engine = DirectHttpEngine(
            allow_private=self._allow_private,
            prefer_ipv4=self._settings.prefer_ipv4,
        )
        self._resolver = UrlCapabilityResolver(
            ytdlp_engine=self._ytdlp_engine,
            direct_engine=self._direct_engine,
            allow_private=self._allow_private,
        )
        self._metadata_service = MetadataService(
            self._resolver,
            allow_private=self._allow_private,
            prefer_ipv4=self._settings.prefer_ipv4,
        )

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @property
    def history_repo(self) -> HistoryRepository:
        return self._history_repo

    @property
    def queue_service(self) -> QueueService:
        return self._queue

    @property
    def migration_report(self) -> MigrationReport:
        return self._migration_report

    def check_dependencies(self) -> list[DependencyStatus]:
        return self._dependency_service.check_all()

    def is_ffmpeg_available(self) -> bool:
        """Return True if a runnable FFmpeg binary is available."""
        return self._ffmpeg.is_ffmpeg_available()

    def is_installing_ffmpeg(self) -> bool:
        """Return True while a one-click FFmpeg installation is in progress."""
        with self._lock:
            return self._installing_ffmpeg

    def install_ffmpeg(self) -> bool:
        """Download and install FFmpeg in the background into the app user data directory."""
        with self._lock:
            if self._installing_ffmpeg or self._shutting_down:
                return False
            self._installing_ffmpeg = True
            cancel_event = threading.Event()
            self._ffmpeg_cancel_event = cancel_event
            worker = FfmpegInstallWorker(self._ffmpeg, cancel_event=cancel_event)
            self._active_workers["ffmpeg_install"] = worker

        worker.signals.progress.connect(self.signals.ffmpeg_install_progress.emit)
        worker.signals.finished.connect(self._on_ffmpeg_install_finished)
        worker.signals.failed.connect(self._on_ffmpeg_install_failed)
        self.signals.ffmpeg_install_started.emit()
        self._pool.start(worker)
        return True

    def _on_ffmpeg_install_finished(self, ffmpeg_path: str) -> None:
        with self._lock:
            self._installing_ffmpeg = False
            self._ffmpeg_cancel_event = None
            self._active_workers.pop("ffmpeg_install", None)
        self.signals.ffmpeg_install_finished.emit(ffmpeg_path)
        self.signals.dependencies_changed.emit()

    def _on_ffmpeg_install_failed(self, error_msg: str) -> None:
        with self._lock:
            self._installing_ffmpeg = False
            self._ffmpeg_cancel_event = None
            self._active_workers.pop("ffmpeg_install", None)
        self.signals.ffmpeg_install_failed.emit(error_msg)
        self.signals.dependencies_changed.emit()

    def update_settings(self, new_settings: AppSettings) -> AppSettings:
        """Persist updated settings, adjust concurrency, and emit settings_changed."""
        saved = self._settings_manager.save(new_settings)
        self._settings_manager.ensure_download_folder(saved)
        ipv4_changed = saved.prefer_ipv4 != self._settings.prefer_ipv4
        self._settings = saved
        self._queue.set_max_concurrency(saved.concurrent_downloads)
        if ipv4_changed:
            self._rebuild_engines()
        self.signals.settings_changed.emit(saved)
        self._dispatch_pending()
        return saved

    def analyze_url(self, url: str, *, allow_playlist: bool = False) -> str:
        """Submit a background MetadataWorker and return the request correlation ID."""
        request_id = str(uuid.uuid4())
        worker = MetadataWorker(
            request_id,
            url,
            self._metadata_service,
            allow_playlist=allow_playlist,
        )
        with self._lock:
            self._active_workers[f"meta:{request_id}"] = worker

        worker.signals.finished.connect(self._on_metadata_finished)
        worker.signals.error.connect(self._on_metadata_error)
        self._pool.start(worker)
        return request_id

    def _on_metadata_finished(
        self,
        request_id: str,
        metadata: ResourceMetadata,
        thumb_bytes: bytes | None,
    ) -> None:
        with self._lock:
            self._active_workers.pop(f"meta:{request_id}", None)
        self.signals.metadata_resolved.emit(request_id, metadata, thumb_bytes)

    def _on_metadata_error(self, request_id: str, error_msg: str) -> None:
        with self._lock:
            self._active_workers.pop(f"meta:{request_id}", None)
        self.signals.metadata_failed.emit(request_id, error_msg)

    def enqueue_download(self, request: DownloadRequest) -> DownloadJob:
        """Add a validated DownloadRequest to the queue, record in history, and dispatch."""
        self._settings_manager.ensure_download_folder(self._settings)
        job = self._queue.enqueue(request)
        self._record_job_history(job)
        self.signals.job_added.emit(job)
        self.signals.queue_changed.emit()
        self.signals.history_updated.emit()
        self._dispatch_pending()
        return job

    def _dispatch_pending(self) -> None:
        if self._shutting_down:
            return
        for job in self._queue.pop_dispatchable_jobs():
            self._start_job_worker(job)

    def _start_job_worker(self, job: DownloadJob) -> None:
        cancel_event = threading.Event()
        pause_event = threading.Event()
        engine = (
            self._ytdlp_engine
            if job.engine_type == EngineType.YTDLP
            else self._direct_engine
        )
        worker = DownloadWorker(job, engine, cancel_event, pause_event)

        with self._lock:
            self._cancel_events[job.job_id] = cancel_event
            self._pause_events[job.job_id] = pause_event
            self._active_workers[job.job_id] = worker

        worker.signals.status_changed.connect(self._on_worker_status_changed)
        worker.signals.progress.connect(self._on_worker_progress)
        worker.signals.completed.connect(self._on_worker_completed)
        worker.signals.paused.connect(self._on_worker_paused)
        worker.signals.cancelled.connect(self._on_worker_cancelled)
        worker.signals.failed.connect(self._on_worker_failed)

        job.started_at = job.started_at or utc_now_iso()
        self.signals.job_updated.emit(job)
        self.signals.queue_changed.emit()
        self._pool.start(worker)

    def _cleanup_worker_refs(self, job_id: str) -> None:
        with self._lock:
            self._cancel_events.pop(job_id, None)
            self._pause_events.pop(job_id, None)
            self._active_workers.pop(job_id, None)

    def _on_worker_status_changed(self, job_id: str, status_str: str) -> None:
        job = self._queue.get_job(job_id)
        if not job:
            return
        job.status = DownloadStatus(status_str)
        if job.progress:
            job.progress.status = job.status
        self._record_job_history(job)
        self.signals.job_updated.emit(job)
        self.signals.queue_changed.emit()

    def _on_worker_progress(self, progress: DownloadProgress) -> None:
        job = self._queue.get_job(progress.job_id)
        if not job:
            return
        job.status = progress.status
        job.progress = progress
        job.can_pause = progress.supports_pause
        job.can_resume = progress.supports_resume
        self.signals.job_updated.emit(job)

    def _on_worker_completed(self, job_id: str, final_path_str: str, file_size: int) -> None:
        self._cleanup_worker_refs(job_id)
        self._queue.release_reservation(job_id)
        job = self._queue.get_job(job_id)
        if job:
            job.status = DownloadStatus.COMPLETED
            job.completed_at = utc_now_iso()
            job.final_path = Path(final_path_str)
            job.can_pause = False
            job.can_resume = False
            if job.progress:
                job.progress.status = DownloadStatus.COMPLETED
                job.progress.percent = 100.0
                job.progress.destination_path = final_path_str
                job.progress.filename = Path(final_path_str).name
                job.progress.total_bytes = file_size or job.progress.total_bytes
                job.progress.downloaded_bytes = file_size or job.progress.downloaded_bytes
            self._record_job_history(job, file_size=file_size)
            self.signals.job_updated.emit(job)
            self.signals.queue_changed.emit()
            self.signals.history_updated.emit()
        self._dispatch_pending()

    def _on_worker_paused(self, job_id: str) -> None:
        self._cleanup_worker_refs(job_id)
        job = self._queue.get_job(job_id)
        if job:
            job.status = DownloadStatus.PAUSED
            if job.progress:
                job.progress.status = DownloadStatus.PAUSED
                job.progress.speed_bps = None
                job.progress.eta_seconds = None
                job.progress.message = "Paused"
            self._record_job_history(job)
            self.signals.job_updated.emit(job)
            self.signals.queue_changed.emit()
            self.signals.history_updated.emit()
        self._dispatch_pending()

    def _on_worker_cancelled(self, job_id: str) -> None:
        self._cleanup_worker_refs(job_id)
        self._queue.release_reservation(job_id)
        job = self._queue.get_job(job_id)
        if job:
            job.status = DownloadStatus.CANCELLED
            job.completed_at = utc_now_iso()
            job.can_pause = False
            job.can_resume = False
            if job.progress:
                job.progress.status = DownloadStatus.CANCELLED
                job.progress.speed_bps = None
                job.progress.eta_seconds = None
                job.progress.message = "Cancelled"
            self._record_job_history(job)
            self.signals.job_updated.emit(job)
            self.signals.queue_changed.emit()
            self.signals.history_updated.emit()
        self._dispatch_pending()

    def _on_worker_failed(self, job_id: str, error_message: str) -> None:
        self._cleanup_worker_refs(job_id)
        self._queue.release_reservation(job_id)
        job = self._queue.get_job(job_id)
        if job:
            job.status = DownloadStatus.FAILED
            job.completed_at = utc_now_iso()
            job.error_message = error_message
            job.can_pause = False
            if job.progress:
                job.progress.status = DownloadStatus.FAILED
                job.progress.speed_bps = None
                job.progress.eta_seconds = None
                job.progress.message = error_message
            self._record_job_history(job)
            self.signals.job_updated.emit(job)
            self.signals.queue_changed.emit()
            self.signals.history_updated.emit()
        self._dispatch_pending()

    def _record_job_history(self, job: DownloadJob, *, file_size: int | None = None) -> None:
        target_path = job.final_path or job.reserved_path
        filename = target_path.name if target_path else job.title
        entry = HistoryEntry(
            id=job.job_id,
            url=job.request.url,
            platform=job.platform,
            title=job.title,
            filename=filename,
            file_path=str(job.final_path) if job.final_path else None,
            format_id=job.format_id,
            format_label=job.format_label,
            file_size=file_size,
            started_at=job.started_at or job.created_at,
            completed_at=job.completed_at,
            status=job.status.value,
            error_details=job.error_message,
        )
        self._history_repo.upsert_entry(entry)

    def pause_job(self, job_id: str) -> bool:
        job = self._queue.get_job(job_id)
        if job is None or not job.can_pause:
            return False
        with self._lock:
            ev = self._pause_events.get(job_id)
        if ev is not None:
            ev.set()
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        job = self._queue.prepare_retry_or_resume(job_id, resume=True)
        if job is None:
            return False
        self._record_job_history(job)
        self.signals.job_updated.emit(job)
        self.signals.queue_changed.emit()
        self._dispatch_pending()
        return True

    def cancel_job(self, job_id: str) -> bool:
        job = self._queue.get_job(job_id)
        if job is None or job.status.is_terminal:
            return False

        with self._lock:
            ev = self._cancel_events.get(job_id)

        if ev is not None:
            ev.set()
            return True

        # Job is still QUEUED or PAUSED (not running inside a worker)
        if job.temp_path and job.temp_path.exists():
            with contextlib.suppress(OSError):
                job.temp_path.unlink()
        if job.reserved_path:
            part = Path(f"{job.reserved_path}.part")
            if part.exists():
                with contextlib.suppress(OSError):
                    part.unlink()

        self._queue.release_reservation(job_id)
        job.status = DownloadStatus.CANCELLED
        job.completed_at = utc_now_iso()
        if job.progress:
            job.progress.status = DownloadStatus.CANCELLED
            job.progress.message = "Cancelled"
        self._record_job_history(job)
        self.signals.job_updated.emit(job)
        self.signals.queue_changed.emit()
        self.signals.history_updated.emit()
        return True

    def retry_job(self, job_id: str) -> bool:
        job = self._queue.prepare_retry_or_resume(job_id, resume=False)
        if job is None:
            return False
        self._record_job_history(job)
        self.signals.job_updated.emit(job)
        self.signals.queue_changed.emit()
        self._dispatch_pending()
        return True

    def remove_completed(self) -> int:
        removed = self._queue.remove_finished()
        if removed:
            self.signals.queue_changed.emit()
        return removed

    def cancel_all(self) -> None:
        for job in self._queue.list_jobs():
            if not job.status.is_terminal:
                self.cancel_job(job.job_id)

    def retry_all_failed(self) -> None:
        for job in self._queue.list_jobs():
            if job.status in {DownloadStatus.FAILED, DownloadStatus.CANCELLED}:
                self.retry_job(job.job_id)

    def list_jobs(self) -> list[DownloadJob]:
        return self._queue.list_jobs()

    def shutdown(self) -> None:
        """Cancel active workers cleanly and wait for thread pool shutdown."""
        self._shutting_down = True
        with self._lock:
            for ev in self._cancel_events.values():
                ev.set()
            if self._ffmpeg_cancel_event is not None:
                self._ffmpeg_cancel_event.set()
        for job in self._queue.list_jobs():
            if job.status in {DownloadStatus.QUEUED, DownloadStatus.WAITING, DownloadStatus.PAUSED}:
                self.cancel_job(job.job_id)
        self._pool.waitForDone(5000)
