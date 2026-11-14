"""Unit tests for QueueService concurrency gating, path reservation, and state lifecycle."""

from __future__ import annotations

from pathlib import Path

from link_downloader.core.enums import (
    DownloadStatus,
    EngineType,
    FormatKind,
    OverwriteBehavior,
    ResourceKind,
)
from link_downloader.core.models import DownloadRequest, FormatOption, ResourceMetadata
from link_downloader.services.queue_service import QueueService


def _make_request(dest_dir: Path, title: str = "Demo File") -> DownloadRequest:
    fmt = FormatOption(
        format_id="direct",
        ext="mp4",
        kind=FormatKind.DIRECT,
        resolution="Video",
        label="Video · MP4",
    )
    meta = ResourceMetadata(
        url="https://example.com/demo.mp4",
        normalized_url="https://example.com/demo.mp4",
        engine_type=EngineType.DIRECT_HTTP,
        resource_kind=ResourceKind.DIRECT_FILE,
        title=title,
        source_platform="example.com",
        hostname="example.com",
        filename="demo.mp4",
        file_extension=".mp4",
        supports_resume=True,
        formats=[fmt],
    )
    return DownloadRequest(
        url=meta.url,
        destination_dir=dest_dir,
        selected_format=fmt,
        overwrite_behavior=OverwriteBehavior.RENAME,
        metadata=meta,
    )


def test_queue_reserves_unique_paths_and_enforces_concurrency(tmp_path: Path) -> None:
    queue = QueueService(max_concurrency=2)
    req = _make_request(tmp_path)

    j1 = queue.enqueue(req)
    j2 = queue.enqueue(req)
    j3 = queue.enqueue(req)

    # Identical concurrent requests must not reserve the same output file path
    assert j1.reserved_path != j2.reserved_path
    assert j2.reserved_path != j3.reserved_path
    assert j1.reserved_path.name == "demo.mp4"
    assert j2.reserved_path.name == "demo (1).mp4"

    batch1 = queue.pop_dispatchable_jobs()
    assert [j.job_id for j in batch1] == [j1.job_id, j2.job_id]
    assert queue.pop_dispatchable_jobs() == []  # concurrency limit = 2

    # Completing job 1 opens slot for job 3
    j1.status = DownloadStatus.COMPLETED
    queue.release_reservation(j1.job_id)
    batch2 = queue.pop_dispatchable_jobs()
    assert [j.job_id for j in batch2] == [j3.job_id]

    removed = queue.remove_finished()
    assert removed == 1
    assert len(queue.list_jobs()) == 2
