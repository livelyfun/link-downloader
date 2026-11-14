"""Unit tests for SettingsManager and idempotent legacy JSON migration."""

from __future__ import annotations

import json
from pathlib import Path

from link_downloader.config.defaults import AppSettings
from link_downloader.config.settings import SettingsManager
from link_downloader.core.enums import OverwriteBehavior, ThemeMode
from link_downloader.database.repository import HistoryRepository
from link_downloader.services.migration_service import LegacyMigrationService


def test_settings_load_save_and_clamp(settings_manager: SettingsManager) -> None:
    assert not settings_manager.exists()
    defaults = settings_manager.load()
    assert defaults.theme == ThemeMode.DARK.value

    custom = AppSettings(
        download_folder="/tmp/custom-dl",
        concurrent_downloads=99,  # should clamp to 5
        overwrite_behavior="invalid",  # falls back to rename
        theme="light",
        auto_convert_mp3=True,
    )
    saved = settings_manager.save(custom)
    assert saved.concurrent_downloads == 5
    assert saved.overwrite_behavior == OverwriteBehavior.RENAME.value
    assert saved.theme == ThemeMode.LIGHT.value

    reloaded = settings_manager.load()
    assert reloaded.download_folder == "/tmp/custom-dl"
    assert reloaded.auto_convert_mp3 is True


def test_legacy_migration_is_idempotent_and_preserves_originals(
    isolated_app_dirs: Path,
    settings_manager: SettingsManager,
    history_repo: HistoryRepository,
) -> None:
    legacy_dir = isolated_app_dirs / "legacy-yt-downloader"
    legacy_dir.mkdir(parents=True, exist_ok=True)

    legacy_cfg = {
        "downloadFolder": "/home/user/Videos/YT",
        "defaultFormat": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "defaultQuality": "1080p",
        "autoConvertMp3": True,
        "concurrentDownloads": 3,
        "theme": "dark",
    }
    legacy_history = [
        {
            "id": "old-1",
            "url": "https://www.youtube.com/watch?v=abc123",
            "title": "Legacy Video One",
            "formatId": "bestvideo+bestaudio/best",
            "status": "completed",
            "filePath": "/home/user/Videos/YT/Legacy Video One.mp4",
            "startedAt": "2026-01-01T10:00:00.000Z",
            "completedAt": "2026-01-01T10:01:00.000Z",
        },
        {
            "id": "old-2",
            "url": "https://www.youtube.com/watch?v=xyz789",
            "title": "Interrupted Legacy Video",
            "formatId": "18",
            "status": "in-progress",
            "filePath": None,
            "error": None,
            "startedAt": "2026-01-02T12:00:00.000Z",
            "completedAt": None,
        },
    ]
    (legacy_dir / "config.json").write_text(json.dumps(legacy_cfg), encoding="utf-8")
    (legacy_dir / "history.json").write_text(json.dumps(legacy_history), encoding="utf-8")

    migrator = LegacyMigrationService(settings_manager, history_repo, legacy_dir=legacy_dir)
    first_report = migrator.migrate_if_needed()

    assert first_report.config_migrated is True
    assert first_report.history_imported_count == 2
    assert first_report.errors == []
    assert (legacy_dir / "config.json").exists()
    assert (legacy_dir / "history.json").exists()
    assert (legacy_dir / "config.json.bak").exists()
    assert (legacy_dir / "history.json.bak").exists()

    loaded = settings_manager.load()
    assert loaded.download_folder == "/home/user/Videos/YT"
    assert loaded.auto_convert_mp3 is True
    assert loaded.concurrent_downloads == 3

    rows = history_repo.list_entries()
    assert len(rows) == 2
    by_id = {r.id: r for r in rows}
    assert by_id["old-1"].file_path == "/home/user/Videos/YT/Legacy Video One.mp4"
    assert by_id["old-1"].platform == "YouTube"
    assert by_id["old-2"].status == "cancelled"

    # Modify settings after migration, then run migration again: must be idempotent and NOT overwrite
    loaded.concurrent_downloads = 4
    settings_manager.save(loaded)

    second_report = migrator.migrate_if_needed()
    assert second_report.config_migrated is False
    assert second_report.history_imported_count == 0
    assert second_report.history_skipped_count == 2
    assert len(history_repo.list_entries()) == 2
    assert settings_manager.load().concurrent_downloads == 4
