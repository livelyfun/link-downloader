"""Cross-platform application directories and bundle asset path helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import PlatformDirs, user_downloads_dir

APP_DIR_NAME = "link-downloader"
APP_AUTHOR = "LinkDownloader"


def _dirs() -> PlatformDirs:
    return PlatformDirs(appname=APP_DIR_NAME, appauthor=APP_AUTHOR, ensure_exists=False)


def get_config_dir() -> Path:
    """Return the platform-appropriate directory for application configuration."""
    override = os.environ.get("LINK_DOWNLOADER_CONFIG_DIR")
    path = Path(override) if override else Path(_dirs().user_config_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir() -> Path:
    """Return the platform-appropriate directory for SQLite history and app data."""
    override = os.environ.get("LINK_DOWNLOADER_DATA_DIR")
    path = Path(override) if override else Path(_dirs().user_data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_cache_dir() -> Path:
    """Return the platform-appropriate directory for temporary cache files."""
    override = os.environ.get("LINK_DOWNLOADER_CACHE_DIR")
    path = Path(override) if override else Path(_dirs().user_cache_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_dir() -> Path:
    """Return the platform-appropriate directory for application logs."""
    override = os.environ.get("LINK_DOWNLOADER_LOG_DIR")
    path = Path(override) if override else Path(_dirs().user_log_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_default_download_dir() -> Path:
    """Return the OS-appropriate default download folder (Downloads/yt-downloads)."""
    try:
        downloads_root = Path(user_downloads_dir())
    except Exception:
        downloads_root = Path.home() / "Downloads"
    return downloads_root / "yt-downloads"


def get_legacy_config_dir() -> Path:
    """Return the legacy Electron application config directory (~/.config/yt-downloader)."""
    override = os.environ.get("LINK_DOWNLOADER_LEGACY_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / "yt-downloader"


def get_assets_dir() -> Path:
    """Resolve the packaged or development assets directory."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "assets"
        if candidate.exists():
            return candidate

    if getattr(sys, "frozen", False):
        exe_parent = Path(sys.executable).resolve().parent
        for candidate in (exe_parent / "assets", exe_parent / "_internal" / "assets"):
            if candidate.exists():
                return candidate

    return Path(__file__).resolve().parents[3] / "assets"


def get_app_icon_path() -> Path | None:
    """Return the best available application icon file path for the current platform."""
    icons_dir = get_assets_dir() / "icons"
    if sys.platform == "win32":
        candidates = ["app_icon.ico", "app_icon.png", "app_icon.svg"]
    else:
        candidates = ["app_icon.png", "app_icon.svg", "app_icon.ico"]
    for name in candidates:
        path = icons_dir / name
        if path.exists():
            return path
    return None
