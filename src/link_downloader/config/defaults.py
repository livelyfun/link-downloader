"""Default application settings and clamping constants."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from link_downloader.core.enums import OverwriteBehavior, ThemeMode
from link_downloader.platform.paths import get_default_download_dir

MIN_CONCURRENT_DOWNLOADS = 1
MAX_CONCURRENT_DOWNLOADS = 5

DEFAULT_FORMAT_PRESETS: tuple[tuple[str, str], ...] = (
    ("Best Quality (Auto)", "bestvideo+bestaudio/best"),
    ("Up to 2160p (4K)", "bestvideo[height<=2160]+bestaudio/best[height<=2160]"),
    ("Up to 1440p", "bestvideo[height<=1440]+bestaudio/best[height<=1440]"),
    ("Up to 1080p", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"),
    ("Up to 720p", "bestvideo[height<=720]+bestaudio/best[height<=720]"),
    ("Up to 480p", "bestvideo[height<=480]+bestaudio/best[height<=480]"),
    ("Audio Only (Best)", "bestaudio/best"),
)

DEFAULT_QUALITY_OPTIONS: tuple[str, ...] = (
    "best",
    "2160p",
    "1440p",
    "1080p",
    "720p",
    "480p",
    "audio",
)


@dataclass(slots=True)
class AppSettings:
    """User configuration persisted as JSON."""

    download_folder: str = field(default_factory=lambda: str(get_default_download_dir()))
    default_format: str = "bestvideo+bestaudio/best"
    default_quality: str = "best"
    auto_convert_mp3: bool = False
    concurrent_downloads: int = 2
    overwrite_behavior: str = OverwriteBehavior.RENAME.value
    auto_sanitize_filenames: bool = True
    prefer_ipv4: bool = True
    theme: str = ThemeMode.LIGHT.value
    legacy_migrated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def download_path(self) -> Path:
        return Path(self.download_folder).expanduser()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        defaults = cls()
        raw_folder = str(data.get("download_folder") or defaults.download_folder).strip()
        raw_format = str(data.get("default_format") or defaults.default_format).strip()
        raw_quality = str(data.get("default_quality") or defaults.default_quality).strip()
        if raw_quality not in DEFAULT_QUALITY_OPTIONS:
            raw_quality = defaults.default_quality

        try:
            concurrency = int(data.get("concurrent_downloads", defaults.concurrent_downloads))
        except (TypeError, ValueError):
            concurrency = defaults.concurrent_downloads
        concurrency = max(MIN_CONCURRENT_DOWNLOADS, min(MAX_CONCURRENT_DOWNLOADS, concurrency))

        raw_overwrite = str(data.get("overwrite_behavior") or defaults.overwrite_behavior).lower()
        if raw_overwrite not in {b.value for b in OverwriteBehavior}:
            raw_overwrite = defaults.overwrite_behavior

        raw_theme = str(data.get("theme") or defaults.theme).lower()
        if raw_theme not in {t.value for t in ThemeMode}:
            raw_theme = defaults.theme

        return cls(
            download_folder=raw_folder,
            default_format=raw_format,
            default_quality=raw_quality,
            auto_convert_mp3=bool(data.get("auto_convert_mp3", defaults.auto_convert_mp3)),
            concurrent_downloads=concurrency,
            overwrite_behavior=raw_overwrite,
            auto_sanitize_filenames=bool(
                data.get("auto_sanitize_filenames", defaults.auto_sanitize_filenames)
            ),
            prefer_ipv4=bool(data.get("prefer_ipv4", defaults.prefer_ipv4)),
            theme=raw_theme,
            legacy_migrated=bool(data.get("legacy_migrated", defaults.legacy_migrated)),
        )
