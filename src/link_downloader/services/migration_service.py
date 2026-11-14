"""Idempotent non-destructive migration from legacy Electron JSON config and history."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from link_downloader.config.defaults import AppSettings
from link_downloader.config.settings import SettingsManager
from link_downloader.core.enums import DownloadStatus
from link_downloader.core.models import HistoryEntry, MigrationReport
from link_downloader.database.repository import HistoryRepository
from link_downloader.platform.paths import get_legacy_config_dir

logger = logging.getLogger(__name__)


def _map_legacy_status(raw_status: Any) -> str:
    value = str(raw_status or "").strip().lower()
    mapping = {
        "in-progress": DownloadStatus.CANCELLED.value,
        "completed": DownloadStatus.COMPLETED.value,
        "failed": DownloadStatus.FAILED.value,
        "cancelled": DownloadStatus.CANCELLED.value,
    }
    return mapping.get(value, value or DownloadStatus.COMPLETED.value)


def _infer_legacy_platform(url: str) -> str:
    lowered = url.lower()
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "YouTube"
    return "Legacy Import"


class LegacyMigrationService:
    """Safely migrates ~/.config/yt-downloader/{config.json,history.json} once."""

    def __init__(
        self,
        settings_manager: SettingsManager,
        history_repo: HistoryRepository,
        legacy_dir: Path | None = None,
    ) -> None:
        self._settings_manager = settings_manager
        self._history_repo = history_repo
        self._legacy_dir = legacy_dir or get_legacy_config_dir()

    def _create_backup(self, src_file: Path, report: MigrationReport) -> None:
        if not src_file.exists():
            return
        backup_path = src_file.with_name(f"{src_file.name}.bak")
        if backup_path.exists():
            return
        try:
            shutil.copy2(src_file, backup_path)
            report.backup_files_created.append(str(backup_path))
        except Exception as exc:
            report.errors.append(f"Could not back up {src_file}: {exc}")

    def migrate_if_needed(self) -> MigrationReport:
        """Import legacy Electron config and history idempotently without destroying originals."""
        report = MigrationReport()
        if not self._legacy_dir.exists():
            return report

        current_settings = self._settings_manager.load()
        settings_existed_before = self._settings_manager.exists()

        legacy_config_path = self._legacy_dir / "config.json"
        legacy_history_path = self._legacy_dir / "history.json"

        # 1. Migrate legacy config only if new settings file does not exist yet (never overwrite user edits)
        if legacy_config_path.exists() and not settings_existed_before and not current_settings.legacy_migrated:
            self._create_backup(legacy_config_path, report)
            try:
                raw_cfg = json.loads(legacy_config_path.read_text(encoding="utf-8"))
                if isinstance(raw_cfg, dict):
                    migrated = AppSettings.from_dict(
                        {
                            "download_folder": raw_cfg.get("downloadFolder", current_settings.download_folder),
                            "default_format": raw_cfg.get("defaultFormat", current_settings.default_format),
                            "default_quality": raw_cfg.get("defaultQuality", current_settings.default_quality),
                            "auto_convert_mp3": raw_cfg.get("autoConvertMp3", current_settings.auto_convert_mp3),
                            "concurrent_downloads": raw_cfg.get(
                                "concurrentDownloads", current_settings.concurrent_downloads
                            ),
                            "theme": raw_cfg.get("theme", current_settings.theme),
                            "legacy_migrated": True,
                        }
                    )
                    self._settings_manager.save(migrated)
                    report.config_migrated = True
            except Exception as exc:
                msg = f"Failed to migrate legacy config {legacy_config_path}: {exc}"
                logger.warning(msg)
                report.errors.append(msg)

        # 2. Migrate legacy history idempotently using INSERT OR IGNORE by ID
        if legacy_history_path.exists():
            self._create_backup(legacy_history_path, report)
            try:
                raw_hist = json.loads(legacy_history_path.read_text(encoding="utf-8"))
                if isinstance(raw_hist, list):
                    for idx, item in enumerate(raw_hist):
                        if not isinstance(item, dict):
                            report.history_skipped_count += 1
                            continue
                        entry_id = str(item.get("id") or f"legacy-{idx}")
                        url = str(item.get("url") or "").strip()
                        title = str(item.get("title") or url or "Legacy Download").strip()
                        file_path = item.get("filePath")
                        filename = Path(file_path).name if file_path else title
                        entry = HistoryEntry(
                            id=entry_id,
                            url=url,
                            platform=_infer_legacy_platform(url),
                            title=title,
                            filename=filename,
                            file_path=str(file_path) if file_path else None,
                            format_id=str(item.get("formatId")) if item.get("formatId") else None,
                            format_label=str(item.get("formatId")) if item.get("formatId") else None,
                            file_size=None,
                            started_at=str(item.get("startedAt") or ""),
                            completed_at=str(item.get("completedAt")) if item.get("completedAt") else None,
                            status=_map_legacy_status(item.get("status")),
                            error_details=str(item.get("error")) if item.get("error") else None,
                        )
                        if self._history_repo.insert_if_absent(entry):
                            report.history_imported_count += 1
                        else:
                            report.history_skipped_count += 1
            except Exception as exc:
                msg = f"Failed to migrate legacy history {legacy_history_path}: {exc}"
                logger.warning(msg)
                report.errors.append(msg)

        if (
            not report.config_migrated
            and not current_settings.legacy_migrated
            and (
                report.history_imported_count > 0
                or legacy_config_path.exists()
                or legacy_history_path.exists()
            )
        ):
            current_settings.legacy_migrated = True
            self._settings_manager.save(current_settings)

        return report
