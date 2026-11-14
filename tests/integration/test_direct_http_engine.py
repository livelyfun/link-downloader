"""Integration tests for DirectHttpEngine against a real local HTTP server."""

from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import httpx
import pytest

from link_downloader.core.enums import DownloadStatus, EngineType, OverwriteBehavior
from link_downloader.core.exceptions import (
    DownloadCancelledError,
    DownloadPausedError,
    FileCollisionError,
    HtmlNotMediaError,
    NetworkDownloadError,
    RedirectBlockedError,
)
from link_downloader.core.models import (
    DownloadJob,
    DownloadProgress,
    DownloadRequest,
    ResourceMetadata,
)
from link_downloader.engines.direct_http_engine import DirectHttpEngine

LARGE_PAYLOAD = bytes(i % 251 for i in range(512 * 1024))
SMALL_PAYLOAD = b"%PDF-1.7\nCross-platform test PDF payload content\n%%EOF\n"


class _TestHttpHandler(BaseHTTPRequestHandler):
    routes: ClassVar[dict[str, bytes]] = {
        "/files/archive": LARGE_PAYLOAD,
        "/files/slow-archive": LARGE_PAYLOAD,
        "/files/report.pdf": SMALL_PAYLOAD,
        "/stream-nosize": b"unsized-stream-chunk-0123456789" * 2048,
        "/no-range.bin": LARGE_PAYLOAD,
    }

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_HEAD(self) -> None:
        if self.path == "/redirect-to-pdf":
            self.send_response(302)
            self.send_header("Location", "/files/report.pdf")
            self.end_headers()
            return
        if self.path == "/page.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", "42")
            self.end_headers()
            return
        if self.path == "/missing":
            self.send_response(404)
            self.end_headers()
            return
        if self.path == "/stream-nosize":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            return

        payload = self.routes.get(self.path)
        if payload is None:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        if self.path in {"/files/archive", "/files/slow-archive"}:
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="archive-v2.zip"')
            self.send_header("Accept-Ranges", "bytes")
        elif self.path == "/files/report.pdf":
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Accept-Ranges", "bytes")
        elif self.path == "/no-range.bin":
            self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/redirect-to-pdf":
            self.send_response(302)
            self.send_header("Location", "/files/report.pdf")
            self.end_headers()
            return
        if self.path == "/page.html":
            body = b"<html><body><h1>Not a video file</h1></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/missing":
            self.send_response(404)
            self.end_headers()
            return
        if self.path == "/stream-nosize":
            body = self.routes["/stream-nosize"]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True
            return

        payload = self.routes.get(self.path)
        if payload is None:
            self.send_response(404)
            self.end_headers()
            return

        range_header = self.headers.get("Range")
        if range_header and self.path in {"/files/archive", "/files/slow-archive", "/files/report.pdf"}:
            start_str = range_header.removeprefix("bytes=").split("-", 1)[0]
            start = int(start_str) if start_str else 0
            if start >= len(payload):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(payload)}")
                self.end_headers()
                return
            sliced = payload[start:]
            self.send_response(206)
            self.send_header("Content-Type", "application/zip" if "archive" in self.path else "application/pdf")
            self.send_header("Content-Range", f"bytes {start}-{len(payload) - 1}/{len(payload)}")
            self.send_header("Content-Length", str(len(sliced)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(sliced)
            return

        self.send_response(200)
        if self.path in {"/files/archive", "/files/slow-archive"}:
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="archive-v2.zip"')
            self.send_header("Accept-Ranges", "bytes")
        elif self.path == "/files/report.pdf":
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Accept-Ranges", "bytes")
        else:
            self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()

        # Stream in slices so cancellation / pause hooks observe multiple chunks
        is_slow = self.path == "/files/slow-archive"
        for offset in range(0, len(payload), 16_384):
            try:
                self.wfile.write(payload[offset : offset + 16_384])
                self.wfile.flush()
                if is_slow:
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError, OSError):
                break


@pytest.fixture
def http_server_url() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TestHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _make_job(
    url: str,
    dest_dir: Path,
    *,
    metadata: ResourceMetadata | None = None,
    overwrite: OverwriteBehavior = OverwriteBehavior.RENAME,
) -> DownloadJob:
    req = DownloadRequest(
        url=url,
        destination_dir=dest_dir,
        overwrite_behavior=overwrite,
        metadata=metadata,
    )
    return DownloadJob(
        job_id="job-http-1",
        request=req,
        title=metadata.title if metadata else "file",
        platform="127.0.0.1",
        engine_type=EngineType.DIRECT_HTTP,
        format_id="direct",
        format_label="Direct File",
    )


def test_probe_and_download_with_content_disposition(
    http_server_url: str,
    tmp_path: Path,
) -> None:
    engine = DirectHttpEngine(allow_private=True, chunk_size=16_384)
    url = f"{http_server_url}/files/archive"

    meta = engine.probe(url)
    assert meta.engine_type is EngineType.DIRECT_HTTP
    assert meta.filename == "archive-v2.zip"
    assert meta.file_extension == ".zip"
    assert meta.total_bytes == len(LARGE_PAYLOAD)
    assert meta.supports_resume is True

    events: list[DownloadProgress] = []
    job = _make_job(url, tmp_path / "out", metadata=meta)
    final_path = engine.download(
        job,
        events.append,
        threading.Event(),
        threading.Event(),
    )

    assert final_path.name == "archive-v2.zip"
    assert final_path.read_bytes() == LARGE_PAYLOAD
    assert not Path(f"{final_path}.part").exists()
    assert events[-1].status is DownloadStatus.COMPLETED
    assert events[-1].percent == pytest.approx(100.0)


def test_download_unsized_stream_without_range_support(
    http_server_url: str,
    tmp_path: Path,
) -> None:
    engine = DirectHttpEngine(allow_private=True, chunk_size=8192)
    url = f"{http_server_url}/stream-nosize"

    meta = engine.probe(url)
    assert meta.total_bytes is None
    assert meta.supports_resume is False

    events: list[DownloadProgress] = []
    job = _make_job(url, tmp_path / "out", metadata=meta)
    final_path = engine.download(
        job,
        events.append,
        threading.Event(),
        threading.Event(),
    )

    assert job.can_pause is False
    assert job.can_resume is False
    assert final_path.read_bytes() == _TestHttpHandler.routes["/stream-nosize"]
    assert events[-1].status is DownloadStatus.COMPLETED


def test_pause_and_resume_with_http_range_206(
    http_server_url: str,
    tmp_path: Path,
) -> None:
    engine = DirectHttpEngine(allow_private=True, chunk_size=16_384)
    url = f"{http_server_url}/files/slow-archive"
    meta = engine.probe(url)
    dest_dir = tmp_path / "out"
    job = _make_job(url, dest_dir, metadata=meta)

    pause_event = threading.Event()
    cancel_event = threading.Event()
    first_events: list[DownloadProgress] = []

    def _pause_after_first_chunk(progress: DownloadProgress) -> None:
        first_events.append(progress)
        if progress.downloaded_bytes > 0:
            pause_event.set()

    with pytest.raises(DownloadPausedError):
        engine.download(job, _pause_after_first_chunk, cancel_event, pause_event)

    expected_dest = dest_dir / "archive-v2.zip"
    part_file = Path(f"{expected_dest}.part")
    assert part_file.exists()
    partial_len = part_file.stat().st_size
    assert 0 < partial_len < len(LARGE_PAYLOAD)

    # Reserve path like QueueService does across pause -> resume cycles
    job.reserved_path = expected_dest
    pause_event.clear()
    resume_events: list[DownloadProgress] = []
    final_path = engine.download(job, resume_events.append, cancel_event, pause_event)

    assert final_path == expected_dest
    assert final_path.read_bytes() == LARGE_PAYLOAD
    assert not part_file.exists()


def test_server_ignoring_range_200_restarts_cleanly_without_corruption(
    http_server_url: str,
    tmp_path: Path,
) -> None:
    engine = DirectHttpEngine(allow_private=True, chunk_size=32_768)
    url = f"{http_server_url}/no-range.bin"
    dest_dir = tmp_path / "out"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Force an existing .part file + metadata claiming resume=True even though server ignores Range
    meta = engine.probe(url)
    meta.supports_resume = True
    part_path = dest_dir / "no-range.bin.part"
    part_path.write_bytes(b"stale-partial-bytes")

    job = _make_job(url, dest_dir, metadata=meta)
    final_path = engine.download(job, lambda _p: None, threading.Event(), threading.Event())

    assert final_path.read_bytes() == LARGE_PAYLOAD
    assert len(final_path.read_bytes()) == len(LARGE_PAYLOAD)


def test_follows_safe_redirect_and_rejects_html_and_404(
    http_server_url: str,
    tmp_path: Path,
) -> None:
    engine = DirectHttpEngine(allow_private=True)

    meta = engine.probe(f"{http_server_url}/redirect-to-pdf")
    assert meta.filename == "report.pdf"
    assert meta.total_bytes == len(SMALL_PAYLOAD)

    job = _make_job(f"{http_server_url}/redirect-to-pdf", tmp_path / "out", metadata=meta)
    downloaded = engine.download(job, lambda _p: None, threading.Event(), threading.Event())
    assert downloaded.read_bytes() == SMALL_PAYLOAD

    with pytest.raises(HtmlNotMediaError):
        engine.probe(f"{http_server_url}/page.html")

    with pytest.raises(HtmlNotMediaError):
        html_job = _make_job(f"{http_server_url}/page.html", tmp_path / "out")
        engine.download(html_job, lambda _p: None, threading.Event(), threading.Event())

    with pytest.raises(NetworkDownloadError, match="404"):
        missing_job = _make_job(f"{http_server_url}/missing", tmp_path / "out")
        engine.download(missing_job, lambda _p: None, threading.Event(), threading.Event())


def test_cancel_mid_download_cleans_up_part_file(
    http_server_url: str,
    tmp_path: Path,
) -> None:
    engine = DirectHttpEngine(allow_private=True, chunk_size=16_384)
    url = f"{http_server_url}/files/slow-archive"
    meta = engine.probe(url)
    dest_dir = tmp_path / "out"
    job = _make_job(url, dest_dir, metadata=meta)

    cancel_event = threading.Event()

    def _cancel_immediately(progress: DownloadProgress) -> None:
        if progress.downloaded_bytes > 0:
            cancel_event.set()

    with pytest.raises(DownloadCancelledError):
        engine.download(job, _cancel_immediately, cancel_event, threading.Event())

    assert not (dest_dir / "archive-v2.zip").exists()
    assert not (dest_dir / "archive-v2.zip.part").exists()


def test_overwrite_behaviors_rename_and_skip(
    http_server_url: str,
    tmp_path: Path,
) -> None:
    engine = DirectHttpEngine(allow_private=True)
    url = f"{http_server_url}/files/report.pdf"
    meta = engine.probe(url)
    dest_dir = tmp_path / "out"
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing = dest_dir / "report.pdf"
    existing.write_bytes(b"existing-pdf")

    rename_job = _make_job(url, dest_dir, metadata=meta, overwrite=OverwriteBehavior.RENAME)
    renamed_path = engine.download(rename_job, lambda _p: None, threading.Event(), threading.Event())
    assert renamed_path.name == "report (1).pdf"
    assert existing.read_bytes() == b"existing-pdf"

    skip_job = _make_job(url, dest_dir, metadata=meta, overwrite=OverwriteBehavior.SKIP)
    with pytest.raises(FileCollisionError):
        engine.download(skip_job, lambda _p: None, threading.Event(), threading.Event())


def test_blocks_redirect_to_private_metadata_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        if host == "public.example.com"
        else [],
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example.com":
            return httpx.Response(
                302,
                headers={"Location": "http://169.254.169.254/latest/meta-data/"},
            )
        return httpx.Response(200, content=b"should-never-reach")

    engine = DirectHttpEngine(
        allow_private=False,
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(RedirectBlockedError):
        engine.probe("https://public.example.com/file.zip")
