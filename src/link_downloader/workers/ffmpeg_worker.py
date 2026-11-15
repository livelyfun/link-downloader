"""Background QRunnable worker for downloading and installing FFmpeg/FFprobe."""

from __future__ import annotations

import logging
import threading

import httpx
from PySide6.QtCore import QRunnable

from link_downloader.core.signals import FfmpegWorkerSignals
from link_downloader.services.ffmpeg_service import FfmpegService

logger = logging.getLogger(__name__)


class FfmpegInstallWorker(QRunnable):
    """Downloads a static FFmpeg build for the current platform off the Qt UI thread."""

    def __init__(
        self,
        ffmpeg_service: FfmpegService,
        *,
        cancel_event: threading.Event | None = None,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self._ffmpeg = ffmpeg_service
        self._cancel_event = cancel_event or threading.Event()
        self.signals = FfmpegWorkerSignals()

    def run(self) -> None:
        try:
            ffmpeg_path, _ffprobe_path = self._ffmpeg.download_and_install(
                progress_callback=self.signals.progress.emit,
                cancel_event=self._cancel_event,
            )
            self.signals.finished.emit(str(ffmpeg_path))
        except InterruptedError:
            self.signals.failed.emit("FFmpeg download was cancelled.")
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP error downloading FFmpeg: %s", exc)
            self.signals.failed.emit(
                "Could not download FFmpeg right now. Please check your internet connection and try again."
            )
        except httpx.RequestError as exc:
            logger.warning("Network error downloading FFmpeg: %s", exc)
            self.signals.failed.emit(
                "Unable to connect to the FFmpeg download server. Check your internet connection and try again."
            )
        except Exception as exc:
            logger.exception("Failed to install FFmpeg")
            self.signals.failed.emit(f"Could not finish setting up FFmpeg: {exc}")
