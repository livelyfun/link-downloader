"""SQLite repository for querying, updating, and clearing download history."""

from __future__ import annotations

from link_downloader.core.models import HistoryEntry
from link_downloader.database.connection import DatabaseConnection
from link_downloader.database.migrations import apply_migrations
from link_downloader.database.models import row_to_history_entry


class HistoryRepository:
    """Thread-safe SQLite persistence repository for download history records."""

    def __init__(self, db: DatabaseConnection) -> None:
        self._db = db
        with self._db.session() as conn:
            apply_migrations(conn)

    def upsert_entry(self, entry: HistoryEntry) -> None:
        """Insert or update a history entry."""
        with self._db.session() as conn:
            conn.execute(
                """
                INSERT INTO download_history (
                    id, url, platform, title, filename, file_path,
                    format_id, format_label, file_size, started_at,
                    completed_at, status, error_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    url = excluded.url,
                    platform = excluded.platform,
                    title = excluded.title,
                    filename = excluded.filename,
                    file_path = COALESCE(excluded.file_path, download_history.file_path),
                    format_id = COALESCE(excluded.format_id, download_history.format_id),
                    format_label = COALESCE(excluded.format_label, download_history.format_label),
                    file_size = COALESCE(excluded.file_size, download_history.file_size),
                    completed_at = COALESCE(excluded.completed_at, download_history.completed_at),
                    status = excluded.status,
                    error_details = excluded.error_details
                """,
                (
                    entry.id,
                    entry.url,
                    entry.platform,
                    entry.title,
                    entry.filename,
                    entry.file_path,
                    entry.format_id,
                    entry.format_label,
                    entry.file_size,
                    entry.started_at,
                    entry.completed_at,
                    entry.status,
                    entry.error_details,
                ),
            )

    def insert_if_absent(self, entry: HistoryEntry) -> bool:
        """Insert a record only if its ID does not already exist (returns True if inserted)."""
        with self._db.session() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO download_history (
                    id, url, platform, title, filename, file_path,
                    format_id, format_label, file_size, started_at,
                    completed_at, status, error_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.url,
                    entry.platform,
                    entry.title,
                    entry.filename,
                    entry.file_path,
                    entry.format_id,
                    entry.format_label,
                    entry.file_size,
                    entry.started_at,
                    entry.completed_at,
                    entry.status,
                    entry.error_details,
                ),
            )
            return cur.rowcount > 0

    def get_entry(self, entry_id: str) -> HistoryEntry | None:
        """Fetch a single history record by ID."""
        with self._db.session() as conn:
            row = conn.execute(
                "SELECT * FROM download_history WHERE id = ?",
                (entry_id,),
            ).fetchone()
            return row_to_history_entry(row) if row is not None else None

    def list_entries(
        self,
        *,
        search_query: str = "",
        status_filter: str = "",
        platform_filter: str = "",
        limit: int = 500,
    ) -> list[HistoryEntry]:
        """List history records ordered newest-first with optional search and filters."""
        clauses: list[str] = []
        params: list[object] = []

        if search_query.strip():
            like = f"%{search_query.strip().lower()}%"
            clauses.append(
                "(LOWER(title) LIKE ? OR LOWER(filename) LIKE ? OR LOWER(url) LIKE ? OR LOWER(platform) LIKE ?)"
            )
            params.extend([like, like, like, like])

        if status_filter.strip() and status_filter.strip().lower() != "all":
            clauses.append("LOWER(status) = ?")
            params.append(status_filter.strip().lower())

        if platform_filter.strip() and platform_filter.strip().lower() != "all":
            clauses.append("LOWER(platform) = ?")
            params.append(platform_filter.strip().lower())

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM download_history {where_sql} "
            "ORDER BY COALESCE(completed_at, started_at) DESC, rowid DESC LIMIT ?"
        )
        params.append(max(1, limit))

        with self._db.session() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [row_to_history_entry(r) for r in rows]

    def get_distinct_platforms(self) -> list[str]:
        """Return distinct source platform names present in history."""
        with self._db.session() as conn:
            rows = conn.execute(
                "SELECT DISTINCT platform FROM download_history WHERE platform != '' ORDER BY LOWER(platform)"
            ).fetchall()
            return [str(r[0]) for r in rows]

    def delete_entry(self, entry_id: str) -> bool:
        """Delete a single entry by ID."""
        with self._db.session() as conn:
            cur = conn.execute("DELETE FROM download_history WHERE id = ?", (entry_id,))
            return cur.rowcount > 0

    def clear_history(self) -> int:
        """Delete all entries from download history and return the removed row count."""
        with self._db.session() as conn:
            cur = conn.execute("DELETE FROM download_history")
            return cur.rowcount
