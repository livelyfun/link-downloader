"""Abstract interface for download and metadata engines."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from link_downloader.core.models import DownloadJob, DownloadProgress, ResourceMetadata

ProgressCallback = Callable[[DownloadProgress], None]


class BaseDownloadEngine(ABC):
    """Contract implemented by yt-dlp and direct HTTP download engines."""

    @abstractmethod
    def probe(self, url: str) -> ResourceMetadata:
        """Inspect the target URL and return normalized resource metadata."""

    @abstractmethod
    def download(
        self,
        job: DownloadJob,
        progress_callback: ProgressCallback,
        cancel_event: threading.Event,
        pause_event: threading.Event,
    ) -> Path:
        """Execute a download job, streaming progress and honoring cancel/pause signals."""
