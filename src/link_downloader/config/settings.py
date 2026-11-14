"""Thread-safe JSON configuration manager."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from link_downloader.config.defaults import AppSettings
from link_downloader.platform.paths import get_config_dir

logger = logging.getLogger(__name__)


class SettingsManager:
    """Reads and atomically writes user settings JSON in the platform config directory."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir or get_config_dir()
        self._config_file = self._config_dir / "settings.json"
        self._lock = threading.RLock()

    @property
    def config_file(self) -> Path:
        return self._config_file

    def exists(self) -> bool:
        return self._config_file.exists()

    def load(self) -> AppSettings:
        """Load settings from JSON, falling back to safe defaults on missing or invalid data."""
        with self._lock:
            if not self._config_file.exists():
                return AppSettings()
            try:
                raw = json.loads(self._config_file.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    return AppSettings()
                return AppSettings.from_dict(raw)
            except Exception:
                logger.warning("Failed to parse %s; using default settings", self._config_file, exc_info=True)
                return AppSettings()

    def save(self, settings: AppSettings) -> AppSettings:
        """Normalize and atomically write settings to disk."""
        with self._lock:
            normalized = AppSettings.from_dict(settings.to_dict())
            self._config_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = self._config_file.with_suffix(".json.tmp")
            payload = json.dumps(normalized.to_dict(), indent=2)
            tmp_file.write_text(payload + "\n", encoding="utf-8")
            os.replace(tmp_file, self._config_file)
            return normalized

    def ensure_download_folder(self, settings: AppSettings) -> Path:
        """Ensure the configured download destination directory exists."""
        target = settings.download_path
        target.mkdir(parents=True, exist_ok=True)
        return target
