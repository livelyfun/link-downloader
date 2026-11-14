"""Row mapping helpers between SQLite records and HistoryEntry domain models."""

from __future__ import annotations

import sqlite3

from link_downloader.core.models import HistoryEntry


def row_to_history_entry(row: sqlite3.Row) -> HistoryEntry:
    """Convert a SQLite row from download_history into a HistoryEntry."""
    return HistoryEntry(
        id=str(row["id"]),
        url=str(row["url"]),
        platform=str(row["platform"]),
        title=str(row["title"]),
        filename=str(row["filename"]),
        file_path=row["file_path"],
        format_id=row["format_id"],
        format_label=row["format_label"],
        file_size=row["file_size"],
        started_at=str(row["started_at"]),
        completed_at=row["completed_at"],
        status=str(row["status"]),
        error_details=row["error_details"],
    )
