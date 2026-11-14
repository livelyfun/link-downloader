"""Pytest global fixtures isolating filesystem paths and providing reusable app fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from link_downloader.config.settings import SettingsManager
from link_downloader.database.connection import DatabaseConnection
from link_downloader.database.repository import HistoryRepository


@pytest.fixture(autouse=True)
def isolated_app_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate config, data, cache, log, and legacy directories inside pytest tmp_path."""
    cfg_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    log_dir = tmp_path / "logs"
    legacy_dir = tmp_path / "legacy-yt-downloader"
    downloads_dir = tmp_path / "downloads"

    monkeypatch.setenv("LINK_DOWNLOADER_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("LINK_DOWNLOADER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LINK_DOWNLOADER_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("LINK_DOWNLOADER_LOG_DIR", str(log_dir))
    monkeypatch.setenv("LINK_DOWNLOADER_LEGACY_DIR", str(legacy_dir))
    downloads_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def settings_manager(isolated_app_dirs: Path) -> SettingsManager:
    return SettingsManager(isolated_app_dirs / "config")


@pytest.fixture
def history_repo(isolated_app_dirs: Path) -> HistoryRepository:
    db = DatabaseConnection(isolated_app_dirs / "data" / "history.db")
    return HistoryRepository(db)
