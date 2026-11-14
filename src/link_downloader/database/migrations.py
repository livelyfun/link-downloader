"""SQLite schema migrations for download history."""

from __future__ import annotations

import sqlite3

MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (
        1,
        "create_download_history",
        """
        CREATE TABLE IF NOT EXISTS download_history (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT,
            format_id TEXT,
            format_label TEXT,
            file_size INTEGER,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            error_details TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_history_status ON download_history(status);
        CREATE INDEX IF NOT EXISTS idx_history_platform ON download_history(platform);
        CREATE INDEX IF NOT EXISTS idx_history_started_at ON download_history(started_at DESC);
        """,
    ),
)


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending SQLite schema migrations idempotently."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    applied = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for version, name, sql in MIGRATIONS:
        if version in applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (version, name),
        )
