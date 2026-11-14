"""Thread-safe SQLite database connection management."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from link_downloader.platform.paths import get_data_dir


class DatabaseConnection:
    """Manages SQLite connections with WAL mode and thread-safe write serialization."""

    def __init__(self, db_path: Path | None = None) -> None:
        data_dir = get_data_dir()
        self._db_path = db_path or (data_dir / "history.db")
        self._lock = threading.RLock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """Yield a thread-locked SQLite connection that commits on success or rolls back."""
        with self._lock:
            conn = self.connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
