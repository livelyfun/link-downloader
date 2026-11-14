"""Typed domain models for metadata, formats, queue jobs, history, and dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from link_downloader.core.enums import (
    DependencyCategory,
    DownloadStatus,
    EngineType,
    FormatKind,
    OverwriteBehavior,
    ResourceKind,
)


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp string."""
    return datetime.now(UTC).isoformat()


def format_bytes(num_bytes: int | float | None) -> str:
    """Format byte counts into human-readable units."""
    if num_bytes is None or num_bytes < 0:
        return "Unknown"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_duration(seconds: int | float | None) -> str:
    """Format duration seconds as M:SS or H:MM:SS."""
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@dataclass(slots=True)
class FormatOption:
    """Represents a selectable format for media extraction or direct file download."""

    format_id: str
    ext: str
    kind: FormatKind
    resolution: str
    height: int | None = None
    width: int | None = None
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize_bytes: int | None = None
    filesize_approx_bytes: int | None = None
    tbr: float | None = None
    abr: float | None = None
    vbr: float | None = None
    requires_ffmpeg: bool = False
    is_auto_merged: bool = False
    convert_to_mp3: bool = False
    label: str = ""
    note: str = ""

    @property
    def effective_size_bytes(self) -> int | None:
        return self.filesize_bytes if self.filesize_bytes is not None else self.filesize_approx_bytes

    @property
    def display_size(self) -> str:
        if self.filesize_bytes is not None:
            return format_bytes(self.filesize_bytes)
        if self.filesize_approx_bytes is not None:
            return f"~{format_bytes(self.filesize_approx_bytes)}"
        return "Varies / Unknown"

    @property
    def codec_summary(self) -> str:
        parts: list[str] = []
        if self.vcodec and self.vcodec != "none":
            parts.append(self.vcodec)
        if self.acodec and self.acodec != "none":
            parts.append(self.acodec)
        return " + ".join(parts) if parts else self.ext.upper()


@dataclass(slots=True)
class ResourceMetadata:
    """Unified metadata returned after probing and resolving a URL."""

    url: str
    normalized_url: str
    engine_type: EngineType
    resource_kind: ResourceKind
    title: str
    source_platform: str
    hostname: str
    uploader: str | None = None
    duration_seconds: float | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    view_count: int | None = None
    upload_date: str | None = None
    formats: list[FormatOption] = field(default_factory=list)
    content_type: str | None = None
    filename: str | None = None
    file_extension: str | None = None
    file_category: str | None = None
    total_bytes: int | None = None
    supports_resume: bool = False
    is_playlist: bool = False
    playlist_count: int | None = None
    extractor_name: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DownloadRequest:
    """User request describing what and how to download."""

    url: str
    destination_dir: Path
    selected_format: FormatOption | None = None
    preferred_filename: str | None = None
    auto_convert_mp3: bool = False
    overwrite_behavior: OverwriteBehavior = OverwriteBehavior.RENAME
    metadata: ResourceMetadata | None = None
    allow_playlist: bool = False
    prefer_ipv4: bool = True


@dataclass(slots=True)
class DownloadProgress:
    """Real-time progress snapshot emitted by a download engine."""

    job_id: str
    status: DownloadStatus
    percent: float | None = None
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    speed_bps: float | None = None
    eta_seconds: int | None = None
    filename: str = ""
    destination_path: str | None = None
    message: str = ""
    supports_pause: bool = False
    supports_resume: bool = False


@dataclass(slots=True)
class DownloadJob:
    """Stateful representation of a queued, active, or completed download."""

    job_id: str
    request: DownloadRequest
    title: str
    platform: str
    engine_type: EngineType
    format_id: str
    format_label: str
    status: DownloadStatus = DownloadStatus.QUEUED
    progress: DownloadProgress | None = None
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    final_path: Path | None = None
    temp_path: Path | None = None
    can_pause: bool = False
    can_resume: bool = False
    reserved_path: Path | None = None


@dataclass(slots=True)
class HistoryEntry:
    """Persisted download history record stored in SQLite."""

    id: str
    url: str
    platform: str
    title: str
    filename: str
    file_path: str | None = None
    format_id: str | None = None
    format_label: str | None = None
    file_size: int | None = None
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    status: str = DownloadStatus.QUEUED.value
    error_details: str | None = None


@dataclass(slots=True)
class DependencyStatus:
    """Diagnostic status of a Python package or external tool."""

    name: str
    category: DependencyCategory
    available: bool
    version: str | None = None
    path: str | None = None
    impact: str = ""
    install_hint: str = ""
    verify_command: str = ""


@dataclass(slots=True)
class MigrationReport:
    """Summary of legacy JSON config and history migration."""

    config_migrated: bool = False
    history_imported_count: int = 0
    history_skipped_count: int = 0
    backup_files_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
