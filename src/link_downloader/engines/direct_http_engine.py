"""Direct HTTP/HTTPS streaming download engine with SSRF, redirect, and Range resume support."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from link_downloader.core.enums import DownloadStatus, EngineType, FormatKind, ResourceKind
from link_downloader.core.exceptions import (
    DownloadCancelledError,
    DownloadPausedError,
    HtmlNotMediaError,
    NetworkDownloadError,
)
from link_downloader.core.models import (
    DownloadJob,
    DownloadProgress,
    FormatOption,
    ResourceMetadata,
    format_bytes,
)
from link_downloader.core.validators import normalize_and_validate_url, validate_redirect_url
from link_downloader.engines.base import BaseDownloadEngine, ProgressCallback
from link_downloader.services.file_service import (
    classify_file_category,
    infer_filename_from_url,
    resolve_collision_safe_path,
)

logger = logging.getLogger(__name__)

_CONTENT_RANGE_TOTAL_RE = re.compile(r"bytes\s+\d+-\d+/(\d+|\*)", re.IGNORECASE)
_HTML_MIME_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _parse_int_header(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value.strip())
        return parsed if parsed >= 0 else None
    except ValueError:
        return None


def _parse_content_range_total(header_value: str | None) -> int | None:
    if not header_value:
        return None
    match = _CONTENT_RANGE_TOTAL_RE.search(header_value)
    if not match or match.group(1) == "*":
        return None
    return _parse_int_header(match.group(1))


def _is_html_response(content_type: str | None, content_disposition: str | None) -> bool:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime not in _HTML_MIME_TYPES:
        return False
    # Allow only if server explicitly serves it as a file attachment
    return not (content_disposition and "attachment" in content_disposition.lower())


class DirectHttpEngine(BaseDownloadEngine):
    """Streams direct HTTP/HTTPS file downloads safely with Range pause/resume."""

    def __init__(
        self,
        *,
        allow_private: bool = False,
        prefer_ipv4: bool = True,
        transport: httpx.BaseTransport | None = None,
        max_redirects: int = 10,
        max_retries: int = 3,
        chunk_size: int = 65_536,
        connect_timeout: float = 10.0,
        read_timeout: float = 25.0,
    ) -> None:
        self._allow_private = allow_private
        self._prefer_ipv4 = prefer_ipv4
        self._transport = transport
        self._max_redirects = max_redirects
        self._max_retries = max_retries
        self._chunk_size = chunk_size
        self._timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=read_timeout,
            pool=connect_timeout,
        )

    def _create_client(self, *, force_ipv4: bool | None = None) -> httpx.Client:
        use_ipv4 = self._prefer_ipv4 if force_ipv4 is None else force_ipv4
        if self._transport is not None:
            transport = self._transport
        elif use_ipv4:
            transport = httpx.HTTPTransport(local_address="0.0.0.0")
        else:
            transport = httpx.HTTPTransport()

        return httpx.Client(
            follow_redirects=False,
            timeout=self._timeout,
            transport=transport,
            headers={"User-Agent": "LinkDownloader/2.0"},
        )

    def _request_with_safe_redirects(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, httpx.Response]:
        strict_dns = (not self._allow_private) and (self._transport is None)
        current_url = normalize_and_validate_url(
            url,
            allow_private=self._allow_private,
            strict_dns=strict_dns,
        )
        current_method = method.upper()

        for _ in range(self._max_redirects + 1):
            req = client.build_request(current_method, current_url, headers=headers)
            resp = client.send(req, stream=True)
            if resp.status_code in _REDIRECT_STATUSES and "location" in resp.headers:
                location = resp.headers["location"]
                resp.close()
                current_url = validate_redirect_url(
                    location,
                    current_url,
                    allow_private=self._allow_private,
                    strict_dns=strict_dns,
                )
                if resp.status_code == 303:
                    current_method = "GET"
                continue
            return current_url, resp

        raise NetworkDownloadError(
            f"Exceeded maximum redirect limit ({self._max_redirects}).",
        )

    def _send_probe_request(self, client: httpx.Client, url: str) -> tuple[str, httpx.Response]:
        final_url, resp = self._request_with_safe_redirects(client, "HEAD", url)
        if resp.status_code in (403, 405, 501):
            resp.close()
            final_url, resp = self._request_with_safe_redirects(
                client,
                "GET",
                final_url,
                headers={"Range": "bytes=0-0"},
            )
        return final_url, resp

    def probe_headers(self, url: str) -> tuple[str, httpx.Headers, int]:
        """Perform a lightweight safe probe returning (final_url, headers, status_code)."""
        last_exc: Exception | None = None
        for attempt_ipv4 in ([True] if self._prefer_ipv4 else [False, True]):
            with self._create_client(force_ipv4=attempt_ipv4) as client:
                try:
                    final_url, resp = self._send_probe_request(client, url)
                    try:
                        headers = httpx.Headers(resp.headers)
                        status_code = resp.status_code
                    finally:
                        resp.close()
                    return final_url, headers, status_code
                except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
                    last_exc = exc
                    if attempt_ipv4:
                        break
                    continue
                except httpx.HTTPError as exc:
                    raise NetworkDownloadError(f"Failed to inspect URL: {exc}") from exc

        raise NetworkDownloadError(f"Connection failed while inspecting URL: {last_exc}")

    def probe(self, url: str) -> ResourceMetadata:
        """Probe a direct file URL and build ResourceMetadata without downloading the body."""
        normalized = normalize_and_validate_url(
            url,
            allow_private=self._allow_private,
            strict_dns=(not self._allow_private) and (self._transport is None),
        )
        final_url, headers, status_code = self.probe_headers(normalized)

        if status_code >= 400:
            raise NetworkDownloadError(
                f"Server responded with HTTP {status_code} for {final_url}.",
            )

        content_type = headers.get("content-type")
        content_disposition = headers.get("content-disposition")
        if _is_html_response(content_type, content_disposition):
            raise HtmlNotMediaError(
                "URL returned an HTML webpage rather than a downloadable file.",
            )

        accept_ranges = headers.get("accept-ranges", "").lower()
        content_range = headers.get("content-range")
        if status_code == 206:
            total_bytes = _parse_content_range_total(content_range)
            supports_resume = True
        else:
            total_bytes = _parse_int_header(headers.get("content-length"))
            supports_resume = "bytes" in accept_ranges

        filename = infer_filename_from_url(
            final_url,
            content_disposition=content_disposition,
            content_type=content_type,
        )
        ext = Path(filename).suffix.lower()
        file_category = classify_file_category(ext, content_type)
        hostname = urlsplit(final_url).hostname or urlsplit(normalized).hostname or "http"

        size_display = format_bytes(total_bytes) if total_bytes is not None else "Unknown size"
        resume_text = "Resumable" if supports_resume else "No Range resume"
        direct_format = FormatOption(
            format_id="direct",
            ext=ext.lstrip(".") or "bin",
            kind=FormatKind.DIRECT,
            resolution=file_category,
            filesize_bytes=total_bytes,
            requires_ffmpeg=False,
            label=f"{file_category} · {ext.lstrip('.').upper() or 'FILE'} · {size_display} ({resume_text})",
        )

        return ResourceMetadata(
            url=url,
            normalized_url=final_url,
            engine_type=EngineType.DIRECT_HTTP,
            resource_kind=ResourceKind.DIRECT_FILE,
            title=filename,
            source_platform=hostname,
            hostname=hostname,
            formats=[direct_format],
            content_type=content_type.split(";", 1)[0].strip() if content_type else None,
            filename=filename,
            file_extension=ext,
            file_category=file_category,
            total_bytes=total_bytes,
            supports_resume=supports_resume,
        )

    def download(
        self,
        job: DownloadJob,
        progress_callback: ProgressCallback,
        cancel_event: threading.Event,
        pause_event: threading.Event,
    ) -> Path:
        """Stream a direct HTTP/HTTPS file to disk using a temporary .part file."""
        meta = job.request.metadata
        supports_resume = meta.supports_resume if meta is not None else False
        default_name = (
            job.request.preferred_filename
            or (meta.filename if meta and meta.filename else None)
            or infer_filename_from_url(job.request.url)
        )

        dest_path = job.reserved_path or resolve_collision_safe_path(
            job.request.destination_dir,
            default_name,
            job.request.overwrite_behavior,
        )
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = Path(f"{dest_path}.part")

        def _cleanup_part() -> None:
            try:
                if part_path.exists():
                    part_path.unlink()
            except OSError:
                logger.debug("Could not remove partial file %s", part_path, exc_info=True)

        if cancel_event.is_set():
            _cleanup_part()
            raise DownloadCancelledError("Download cancelled before starting.")

        attempt = 0
        while True:
            if cancel_event.is_set():
                _cleanup_part()
                raise DownloadCancelledError("Download cancelled.")

            existing_size = part_path.stat().st_size if (supports_resume and part_path.exists()) else 0
            req_headers: dict[str, str] = {}
            if existing_size > 0:
                req_headers["Range"] = f"bytes={existing_size}-"

            try:
                with self._create_client() as client:
                    final_url, resp = self._request_with_safe_redirects(
                        client,
                        "GET",
                        job.request.url,
                        headers=req_headers or None,
                    )
                    try:
                        if resp.status_code == 416 and existing_size > 0:
                            resp.close()
                            _cleanup_part()
                            existing_size = 0
                            attempt += 1
                            if attempt <= self._max_retries:
                                continue
                            raise NetworkDownloadError("Server rejected resume range (HTTP 416).")

                        if resp.status_code >= 400:
                            raise NetworkDownloadError(
                                f"Server returned HTTP {resp.status_code} for {final_url}.",
                            )

                        content_type = resp.headers.get("content-type")
                        content_disp = resp.headers.get("content-disposition")
                        if _is_html_response(content_type, content_disp):
                            raise HtmlNotMediaError(
                                "Target resolved to an HTML webpage instead of a downloadable file.",
                            )

                        accept_ranges = resp.headers.get("accept-ranges", "").lower()
                        is_partial = resp.status_code == 206
                        if is_partial:
                            supports_resume = True
                            total_bytes = _parse_content_range_total(resp.headers.get("content-range"))
                            if total_bytes is None:
                                cl = _parse_int_header(resp.headers.get("content-length"))
                                total_bytes = (existing_size + cl) if cl is not None else None
                            file_mode = "ab"
                            downloaded = existing_size
                        else:
                            if "bytes" in accept_ranges:
                                supports_resume = True
                            total_bytes = _parse_int_header(resp.headers.get("content-length"))
                            file_mode = "wb"
                            downloaded = 0

                        job.can_pause = supports_resume
                        job.can_resume = supports_resume
                        job.temp_path = part_path

                        last_report_time = time.monotonic()
                        window_bytes = 0
                        speed_bps: float | None = None

                        progress_callback(
                            DownloadProgress(
                                job_id=job.job_id,
                                status=DownloadStatus.DOWNLOADING,
                                percent=(downloaded / total_bytes * 100.0) if total_bytes else None,
                                downloaded_bytes=downloaded,
                                total_bytes=total_bytes,
                                speed_bps=None,
                                eta_seconds=None,
                                filename=dest_path.name,
                                destination_path=str(dest_path),
                                supports_pause=supports_resume,
                                supports_resume=supports_resume,
                            )
                        )

                        with part_path.open(file_mode) as handle:
                            for chunk in resp.iter_bytes(chunk_size=self._chunk_size):
                                if cancel_event.is_set():
                                    handle.close()
                                    _cleanup_part()
                                    raise DownloadCancelledError("Download cancelled.")

                                if pause_event.is_set():
                                    handle.flush()
                                    handle.close()
                                    if not supports_resume:
                                        _cleanup_part()
                                        raise NetworkDownloadError(
                                            "Server does not support pausing/resuming this download.",
                                        )
                                    raise DownloadPausedError("Download paused.")

                                if not chunk:
                                    continue

                                handle.write(chunk)
                                chunk_len = len(chunk)
                                downloaded += chunk_len
                                window_bytes += chunk_len

                                now = time.monotonic()
                                elapsed = now - last_report_time
                                if elapsed >= 0.15:
                                    instant_speed = window_bytes / elapsed
                                    speed_bps = (
                                        instant_speed
                                        if speed_bps is None
                                        else (0.4 * instant_speed + 0.6 * speed_bps)
                                    )
                                    eta = (
                                        int((total_bytes - downloaded) / speed_bps)
                                        if (total_bytes and speed_bps and speed_bps > 0 and total_bytes >= downloaded)
                                        else None
                                    )
                                    pct = (
                                        min(100.0, downloaded / total_bytes * 100.0)
                                        if total_bytes and total_bytes > 0
                                        else None
                                    )
                                    progress_callback(
                                        DownloadProgress(
                                            job_id=job.job_id,
                                            status=DownloadStatus.DOWNLOADING,
                                            percent=pct,
                                            downloaded_bytes=downloaded,
                                            total_bytes=total_bytes,
                                            speed_bps=speed_bps,
                                            eta_seconds=eta,
                                            filename=dest_path.name,
                                            destination_path=str(dest_path),
                                            supports_pause=supports_resume,
                                            supports_resume=supports_resume,
                                        )
                                    )
                                    last_report_time = now
                                    window_bytes = 0

                            handle.flush()
                            os.fsync(handle.fileno())

                        if total_bytes is not None and downloaded < total_bytes:
                            raise httpx.RemoteProtocolError(
                                f"Stream ended prematurely at {downloaded} of {total_bytes} bytes.",
                            )

                        os.replace(part_path, dest_path)
                        progress_callback(
                            DownloadProgress(
                                job_id=job.job_id,
                                status=DownloadStatus.COMPLETED,
                                percent=100.0,
                                downloaded_bytes=downloaded,
                                total_bytes=total_bytes if total_bytes is not None else downloaded,
                                speed_bps=speed_bps,
                                eta_seconds=0,
                                filename=dest_path.name,
                                destination_path=str(dest_path),
                                supports_pause=False,
                                supports_resume=False,
                            )
                        )
                        return dest_path
                    finally:
                        resp.close()

            except (DownloadCancelledError, DownloadPausedError, HtmlNotMediaError):
                raise
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                attempt += 1
                if attempt <= self._max_retries and not cancel_event.is_set() and not pause_event.is_set():
                    logger.warning(
                        "Transient error downloading %s (attempt %d/%d): %s",
                        job.request.url,
                        attempt,
                        self._max_retries,
                        exc,
                    )
                    time.sleep(min(1.5, 0.3 * attempt))
                    continue
                if not supports_resume:
                    _cleanup_part()
                raise NetworkDownloadError(f"Network download failed: {exc}") from exc
            except NetworkDownloadError:
                if not supports_resume:
                    _cleanup_part()
                raise
            except OSError as exc:
                _cleanup_part()
                raise NetworkDownloadError(f"Failed writing downloaded file: {exc}") from exc
