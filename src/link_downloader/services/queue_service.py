"""Thread-safe download queue state, concurrency limiting, and destination path reservation."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from link_downloader.core.enums import DownloadStatus, EngineType
from link_downloader.core.models import DownloadJob, DownloadProgress, DownloadRequest
from link_downloader.services.file_service import (
    infer_filename_from_url,
    resolve_collision_safe_path,
    sanitize_filename,
)


class QueueService:
    """Maintains queued, active, paused, and finished jobs with collision-free paths."""

    def __init__(self, max_concurrency: int = 2) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, DownloadJob] = {}
        self._reserved_paths: set[Path] = set()
        self._max_concurrency = max(1, min(5, max_concurrency))

    @property
    def max_concurrency(self) -> int:
        with self._lock:
            return self._max_concurrency

    def set_max_concurrency(self, value: int) -> None:
        with self._lock:
            self._max_concurrency = max(1, min(5, int(value)))

    def _compute_target_filename(self, request: DownloadRequest) -> str:
        meta = request.metadata
        fmt = request.selected_format
        if request.preferred_filename:
            candidate = sanitize_filename(request.preferred_filename)
            if not Path(candidate).suffix and fmt and fmt.ext:
                candidate = f"{candidate}.{fmt.ext}"
            elif not Path(candidate).suffix and meta and meta.file_extension:
                candidate = f"{candidate}{meta.file_extension}"
            return sanitize_filename(candidate)

        if meta is not None:
            if meta.engine_type == EngineType.DIRECT_HTTP and meta.filename:
                return sanitize_filename(meta.filename)
            ext = "mp3" if (request.auto_convert_mp3 or (fmt and fmt.convert_to_mp3)) else (
                fmt.ext if fmt and fmt.ext else "mp4"
            )
            stem = sanitize_filename(meta.title or "media")
            return sanitize_filename(f"{Path(stem).stem or stem}.{ext}")

        return infer_filename_from_url(request.url)

    def reserve_path_for_request(self, request: DownloadRequest) -> Path:
        """Reserve a collision-safe destination path across disk and active queue entries."""
        with self._lock:
            filename = self._compute_target_filename(request)
            reserved = resolve_collision_safe_path(
                request.destination_dir,
                filename,
                request.overwrite_behavior,
                reserved_paths=self._reserved_paths,
            )
            self._reserved_paths.add(reserved)
            return reserved

    def enqueue(self, request: DownloadRequest) -> DownloadJob:
        """Create and queue a new DownloadJob with a reserved destination path."""
        with self._lock:
            job_id = str(uuid.uuid4())
            meta = request.metadata
            fmt = request.selected_format
            reserved = self.reserve_path_for_request(request)

            engine_type = meta.engine_type if meta is not None else EngineType.DIRECT_HTTP
            title = (
                request.preferred_filename
                or (meta.title if meta and meta.title else None)
                or reserved.name
            )
            platform = meta.source_platform if meta is not None else "Direct HTTP"
            format_id = fmt.format_id if fmt else "direct"
            format_label = fmt.label if fmt and fmt.label else format_id
            supports_pause = (
                True
                if engine_type == EngineType.YTDLP
                else bool(meta.supports_resume if meta else False)
            )

            job = DownloadJob(
                job_id=job_id,
                request=request,
                title=title,
                platform=platform,
                engine_type=engine_type,
                format_id=format_id,
                format_label=format_label,
                status=DownloadStatus.QUEUED,
                progress=DownloadProgress(
                    job_id=job_id,
                    status=DownloadStatus.QUEUED,
                    percent=0.0,
                    filename=reserved.name,
                    destination_path=str(reserved),
                    supports_pause=supports_pause,
                    supports_resume=supports_pause,
                ),
                can_pause=supports_pause,
                can_resume=supports_pause,
                reserved_path=reserved,
            )
            self._jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[DownloadJob]:
        with self._lock:
            return list(self._jobs.values())

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status.is_active)

    def queued_count(self) -> int:
        with self._lock:
            return sum(
                1
                for j in self._jobs.values()
                if j.status in {DownloadStatus.QUEUED, DownloadStatus.WAITING}
            )

    def pop_dispatchable_jobs(self) -> list[DownloadJob]:
        """Mark up to available concurrency slots of QUEUED jobs as WAITING to launch."""
        with self._lock:
            running = sum(
                1
                for j in self._jobs.values()
                if j.status in {DownloadStatus.RESOLVING, DownloadStatus.DOWNLOADING, DownloadStatus.PROCESSING, DownloadStatus.WAITING}
            )
            available_slots = max(0, self._max_concurrency - running)
            if available_slots <= 0:
                return []

            to_start: list[DownloadJob] = []
            for job in self._jobs.values():
                if job.status == DownloadStatus.QUEUED:
                    job.status = DownloadStatus.WAITING
                    if job.progress:
                        job.progress.status = DownloadStatus.WAITING
                    to_start.append(job)
                    if len(to_start) >= available_slots:
                        break
            return to_start

    def release_reservation(self, job_id: str) -> None:
        """Release the destination path reservation when a job finishes or cancels."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.reserved_path is not None:
                self._reserved_paths.discard(job.reserved_path)

    def prepare_retry_or_resume(self, job_id: str, *, resume: bool = False) -> DownloadJob | None:
        """Reset a failed/cancelled/paused job back to QUEUED, re-reserving a path if needed."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if resume and job.status != DownloadStatus.PAUSED:
                return None
            if not resume and job.status not in {DownloadStatus.FAILED, DownloadStatus.CANCELLED}:
                return None

            if job.reserved_path is None or job.reserved_path not in self._reserved_paths:
                if not resume:
                    job.reserved_path = self.reserve_path_for_request(job.request)
                elif job.reserved_path is not None:
                    self._reserved_paths.add(job.reserved_path)

            job.status = DownloadStatus.QUEUED
            job.error_message = None
            if job.progress:
                job.progress.status = DownloadStatus.QUEUED
                job.progress.message = "Resuming..." if resume else "Retrying..."
            return job

    def remove_finished(self) -> int:
        """Remove completed, cancelled, and failed jobs from the active queue view."""
        with self._lock:
            removable = [
                jid for jid, job in self._jobs.items() if job.status.is_terminal
            ]
            for jid in removable:
                self.release_reservation(jid)
                del self._jobs[jid]
            return len(removable)

    def remove_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status.is_active:
                return False
            self.release_reservation(job_id)
            del self._jobs[job_id]
            return True
