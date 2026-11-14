"""Background QRunnable worker for non-blocking URL analysis and metadata probing."""

from __future__ import annotations

import logging

from PySide6.QtCore import QRunnable

from link_downloader.core.exceptions import LinkDownloaderError
from link_downloader.core.signals import MetadataWorkerSignals
from link_downloader.services.metadata_service import MetadataService

logger = logging.getLogger(__name__)


class MetadataWorker(QRunnable):
    """Runs URL capability resolution and thumbnail loading off the Qt GUI thread."""

    def __init__(
        self,
        request_id: str,
        url: str,
        metadata_service: MetadataService,
        *,
        allow_playlist: bool = False,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.request_id = request_id
        self.url = url
        self._service = metadata_service
        self._allow_playlist = allow_playlist
        self.signals = MetadataWorkerSignals()

    def run(self) -> None:
        try:
            metadata = self._service.resolve(self.url, allow_playlist=self._allow_playlist)
            thumb_bytes = self._service.fetch_thumbnail_bytes(metadata.thumbnail_url)
            self.signals.finished.emit(self.request_id, metadata, thumb_bytes)
        except LinkDownloaderError as exc:
            self.signals.error.emit(self.request_id, exc.message)
        except Exception as exc:
            logger.exception("Unhandled error resolving metadata for %s", self.url)
            self.signals.error.emit(self.request_id, f"Unexpected error analyzing URL: {exc}")
