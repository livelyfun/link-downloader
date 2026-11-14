"""Domain exception hierarchy for Link Downloader."""

from __future__ import annotations


class LinkDownloaderError(Exception):
    """Base exception carrying a user-friendly explanation."""

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or message


class ValidationError(LinkDownloaderError):
    """Raised when user-supplied URL or settings input is invalid."""


class UnsafeUrlError(ValidationError):
    """Raised when a URL targets a blocked protocol, host, or private/reserved network."""


class RedirectBlockedError(UnsafeUrlError):
    """Raised when an HTTP redirect targets an unsafe or disallowed destination."""


class UnsupportedResourceError(LinkDownloaderError):
    """Raised when a URL does not point to a supported media stream or downloadable file."""


class HtmlNotMediaError(UnsupportedResourceError):
    """Raised when a URL resolves to an HTML webpage rather than a downloadable file."""


class ExtractionError(LinkDownloaderError):
    """Raised when yt-dlp metadata extraction or media download fails."""


class DownloadCancelledError(LinkDownloaderError):
    """Raised internally when a download is cancelled by the user or shutdown."""


class DownloadPausedError(LinkDownloaderError):
    """Raised internally when a resumable download is paused by the user."""


class NetworkDownloadError(LinkDownloaderError):
    """Raised when direct HTTP downloading fails due to network or HTTP status errors."""


class DependencyMissingError(LinkDownloaderError):
    """Raised when a required external tool or Python package is unavailable."""


class FileCollisionError(LinkDownloaderError):
    """Raised when a destination file already exists and skip/collision policy applies."""
