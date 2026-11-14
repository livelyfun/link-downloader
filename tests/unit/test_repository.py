"""Unit tests for SQLite HistoryRepository CRUD, search, and filters."""

from __future__ import annotations

from link_downloader.core.models import HistoryEntry
from link_downloader.database.repository import HistoryRepository


def test_history_repository_crud_search_and_filters(history_repo: HistoryRepository) -> None:
    e1 = HistoryEntry(
        id="h1",
        url="https://youtube.com/watch?v=1",
        platform="YouTube",
        title="Python Desktop Guide",
        filename="Python Desktop Guide.mp4",
        file_path="/tmp/Python Desktop Guide.mp4",
        format_id="137+140",
        format_label="1080p",
        file_size=102400,
        started_at="2026-05-01T10:00:00+00:00",
        completed_at="2026-05-01T10:02:00+00:00",
        status="completed",
    )
    e2 = HistoryEntry(
        id="h2",
        url="https://cdn.example.com/archive.zip",
        platform="cdn.example.com",
        title="archive.zip",
        filename="archive.zip",
        started_at="2026-05-02T10:00:00+00:00",
        status="failed",
        error_details="HTTP 404",
    )
    history_repo.upsert_entry(e1)
    history_repo.upsert_entry(e2)

    assert len(history_repo.list_entries()) == 2
    assert history_repo.get_distinct_platforms() == ["cdn.example.com", "YouTube"]

    # Search
    assert [e.id for e in history_repo.list_entries(search_query="python")] == ["h1"]
    assert [e.id for e in history_repo.list_entries(search_query="archive.zip")] == ["h2"]

    # Status filter
    assert [e.id for e in history_repo.list_entries(status_filter="failed")] == ["h2"]

    # Platform filter
    assert [e.id for e in history_repo.list_entries(platform_filter="YouTube")] == ["h1"]

    # Upsert update
    e2.status = "completed"
    e2.error_details = None
    history_repo.upsert_entry(e2)
    assert history_repo.get_entry("h2").status == "completed"

    # Delete single and clear
    assert history_repo.delete_entry("h1") is True
    assert len(history_repo.list_entries()) == 1
    assert history_repo.clear_history() == 1
    assert history_repo.list_entries() == []
