"""Central URL capability resolver selecting between yt-dlp and direct HTTP engines."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlsplit

from link_downloader.core.exceptions import (
    HtmlNotMediaError,
    NetworkDownloadError,
    UnsupportedResourceError,
)
from link_downloader.core.models import ResourceMetadata
from link_downloader.core.validators import normalize_and_validate_url
from link_downloader.engines.direct_http_engine import DirectHttpEngine, _is_html_response
from link_downloader.engines.ytdlp_engine import YtDlpEngine
from link_downloader.services.file_service import DIRECT_FILE_EXTENSIONS

logger = logging.getLogger(__name__)


class UrlCapabilityResolver:
    """Routes URLs to specialized yt-dlp extractors, direct HTTP downloads, or generic page probing."""

    def __init__(
        self,
        *,
        ytdlp_engine: YtDlpEngine,
        direct_engine: DirectHttpEngine,
        allow_private: bool = False,
    ) -> None:
        self._ytdlp = ytdlp_engine
        self._direct = direct_engine
        self._allow_private = allow_private

    def resolve(self, raw_url: str, *, allow_playlist: bool = False) -> ResourceMetadata:
        """Validate a URL, determine the capable engine, and return normalized metadata."""
        normalized = normalize_and_validate_url(
            raw_url,
            allow_private=self._allow_private,
            strict_dns=False,
        )

        # 1. Specialized yt-dlp platform extractor match (excluding GenericIE)
        has_specialized, extractor_name = self._ytdlp.is_specialized_url(normalized)
        if has_specialized:
            logger.debug("URL matched specialized yt-dlp extractor '%s': %s", extractor_name, normalized)
            return self._ytdlp.probe(normalized, allow_playlist=allow_playlist, generic_mode=False)

        # 2. Inspect HTTP response headers safely to distinguish direct files from HTML pages
        url_ext = Path(urlsplit(normalized).path).suffix.lower()
        try:
            final_url, headers, status_code = self._direct.probe_headers(normalized)
        except NetworkDownloadError:
            # If direct HTTP probe fails on a link with a non-file extension, attempt generic extraction
            if url_ext not in DIRECT_FILE_EXTENSIONS:
                return self._attempt_generic_extraction(normalized, allow_playlist=allow_playlist)
            raise

        if status_code >= 400:
            raise NetworkDownloadError(
                f"Server responded with HTTP {status_code} while inspecting the URL.",
            )

        content_type = headers.get("content-type")
        content_disposition = headers.get("content-disposition")

        if not _is_html_response(content_type, content_disposition):
            logger.debug("URL resolved as direct HTTP download (%s): %s", content_type, final_url)
            return self._direct.probe(final_url)

        # 3. Generic webpage: attempt yt-dlp extraction; never save raw HTML as a video
        return self._attempt_generic_extraction(final_url, allow_playlist=allow_playlist)

    def _attempt_generic_extraction(self, url: str, *, allow_playlist: bool) -> ResourceMetadata:
        logger.debug("Attempting generic webpage media extraction for: %s", url)
        try:
            return self._ytdlp.probe(url, allow_playlist=allow_playlist, generic_mode=True)
        except UnsupportedResourceError as exc:
            raise HtmlNotMediaError(
                "This webpage does not expose supported downloadable media streams, "
                "and saving raw HTML webpages as media is blocked.",
                details=exc.details,
            ) from exc
