"""Enumerations shared across engines, services, persistence, and UI."""

from __future__ import annotations

from enum import StrEnum


class EngineType(StrEnum):
    """Supported download/extraction engine identifiers."""

    YTDLP = "ytdlp"
    DIRECT_HTTP = "direct_http"
    GENERIC_WEB = "generic_web"
    UNSUPPORTED = "unsupported"


class ResourceKind(StrEnum):
    """High-level classification of a resolved URL."""

    VIDEO_PLATFORM = "video_platform"
    AUDIO_PLATFORM = "audio_platform"
    DIRECT_FILE = "direct_file"
    GENERIC_MEDIA_PAGE = "generic_media_page"
    PLAYLIST = "playlist"
    UNKNOWN = "unknown"


class DownloadStatus(StrEnum):
    """Lifecycle states for a download job."""

    RESOLVING = "resolving"
    WAITING = "waiting"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {
            DownloadStatus.COMPLETED,
            DownloadStatus.CANCELLED,
            DownloadStatus.FAILED,
        }

    @property
    def is_active(self) -> bool:
        return self in {
            DownloadStatus.RESOLVING,
            DownloadStatus.DOWNLOADING,
            DownloadStatus.PROCESSING,
        }


class FormatKind(StrEnum):
    """Classification of a downloadable media or direct format."""

    VIDEO_AUDIO = "video+audio"
    VIDEO_ONLY = "video-only"
    AUDIO_ONLY = "audio-only"
    DIRECT = "direct"


class OverwriteBehavior(StrEnum):
    """Behavior when the target filename already exists on disk."""

    RENAME = "rename"
    OVERWRITE = "overwrite"
    SKIP = "skip"


class ThemeMode(StrEnum):
    """Supported application color themes."""

    DARK = "dark"
    LIGHT = "light"


class DependencyCategory(StrEnum):
    """Importance level of a runtime or external dependency."""

    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"
