"""Background QRunnable worker executing a queued download job."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QRunnable

from link_downloader.core.enums import DownloadStatus
from link_downloader.core.exceptions import (
    DownloadCancelledError,
    DownloadPausedError,
    LinkDownloaderError,
)
from link_downloader.core.models import DownloadJob, DownloadProgress
from link_downloader.core.signals import DownloadWorkerSignals
from link_downloader.engines.base import BaseDownloadEngine

logger = logging.getLogger(__name__)


class DownloadWorker(QRunnable):
    """Executes a single DownloadJob inside QThreadPool with cooperative cancel/pause."""

    def __init__(
        self,
        job: DownloadJob,
        engine: BaseDownloadEngine,
        cancel_event: threading.Event,
        pause_event: threading.Event,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.job = job
        self._engine = engine
        self._cancel_event = cancel_event
        self._pause_event = pause_event
        self.signals = DownloadWorkerSignals()

    def run(self) -> None:
        job_id = self.job.job_id
        self.signals.status_changed.emit(job_id, DownloadStatus.DOWNLOADING.value)

        def _on_progress(progress: DownloadProgress) -> None:
            self.signals.progress.emit(progress)

        try:
            final_path = self._engine.download(
                self.job,
                _on_progress,
                self._cancel_event,
                self._pause_event,
            )
            file_size = final_path.stat().st_size if final_path.exists() else 0
            self.signals.completed.emit(job_id, str(final_path), int(file_size))
        except DownloadCancelledError:
            self.signals.cancelled.emit(job_id)
        except DownloadPausedError:
            self.signals.paused.emit(job_id)
        except LinkDownloaderError as exc:
            self.signals.failed.emit(job_id, exc.message)
        except Exception as exc:
            logger.exception("Unhandled download worker exception for job %s", job_id)
            self.signals.failed.emit(job_id, f"Unexpected download error: {exc}")
