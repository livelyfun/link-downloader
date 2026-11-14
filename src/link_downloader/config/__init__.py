"""Configuration package exports."""

from link_downloader.config.defaults import (
    DEFAULT_FORMAT_PRESETS,
    DEFAULT_QUALITY_OPTIONS,
    MAX_CONCURRENT_DOWNLOADS,
    MIN_CONCURRENT_DOWNLOADS,
    AppSettings,
)
from link_downloader.config.settings import SettingsManager

__all__ = [
    "DEFAULT_FORMAT_PRESETS",
    "DEFAULT_QUALITY_OPTIONS",
    "MAX_CONCURRENT_DOWNLOADS",
    "MIN_CONCURRENT_DOWNLOADS",
    "AppSettings",
    "SettingsManager",
]
