"""Unit tests for UrlCapabilityResolver routing across yt-dlp, direct HTTP, and HTML pages."""

from __future__ import annotations

import httpx
import pytest

from link_downloader.core.enums import EngineType, FormatKind, ResourceKind
from link_downloader.core.exceptions import HtmlNotMediaError, UnsupportedResourceError
from link_downloader.core.models import FormatOption, ResourceMetadata
from link_downloader.engines.direct_http_engine import DirectHttpEngine
from link_downloader.engines.resolver import UrlCapabilityResolver
from link_downloader.engines.ytdlp_engine import YtDlpEngine


class _FakeYtDlpEngine(YtDlpEngine):
    def __init__(self, *, specialized_hosts: set[str], generic_success: bool = False) -> None:
        super().__init__(allow_private=False, prefer_ipv4=True)
        self._hosts = specialized_hosts
        self._generic_success = generic_success
        self.probe_calls: list[tuple[str, bool]] = []

    def is_specialized_url(self, url: str) -> tuple[bool, str | None]:
        for h in self._hosts:
            if h in url:
                return True, h
        return False, None

    def probe(self, url: str, *, allow_playlist: bool = False, generic_mode: bool = False) -> ResourceMetadata:
        self.probe_calls.append((url, generic_mode))
        if generic_mode and not self._generic_success:
            raise UnsupportedResourceError("No streams found")
        return ResourceMetadata(
            url=url,
            normalized_url=url,
            engine_type=EngineType.YTDLP,
            resource_kind=(
                ResourceKind.GENERIC_MEDIA_PAGE if generic_mode else ResourceKind.VIDEO_PLATFORM
            ),
            title="Mocked Media",
            source_platform="YouTube" if not generic_mode else "Webpage Media",
            hostname="example.com",
            formats=[
                FormatOption(
                    format_id="best",
                    ext="mp4",
                    kind=FormatKind.VIDEO_AUDIO,
                    resolution="720p",
                    label="720p · MP4",
                )
            ],
        )


def test_resolver_routes_specialized_ytdlp_urls() -> None:
    fake_yt = _FakeYtDlpEngine(specialized_hosts={"youtube.com", "vimeo.com", "soundcloud.com"})
    direct = DirectHttpEngine(
        transport=httpx.MockTransport(lambda req: httpx.Response(200)),
    )
    resolver = UrlCapabilityResolver(ytdlp_engine=fake_yt, direct_engine=direct)

    meta = resolver.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert meta.engine_type == EngineType.YTDLP
    assert meta.resource_kind == ResourceKind.VIDEO_PLATFORM
    assert fake_yt.probe_calls[-1][1] is False


def test_resolver_routes_direct_file_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/pdf",
                "Content-Length": "4096",
                "Accept-Ranges": "bytes",
                "Content-Disposition": 'attachment; filename="manual.pdf"',
            },
        )

    fake_yt = _FakeYtDlpEngine(specialized_hosts={"youtube.com"})
    direct = DirectHttpEngine(transport=httpx.MockTransport(handler))
    resolver = UrlCapabilityResolver(ytdlp_engine=fake_yt, direct_engine=direct)

    meta = resolver.resolve("https://files.example.com/download?id=99")
    assert meta.engine_type == EngineType.DIRECT_HTTP
    assert meta.resource_kind == ResourceKind.DIRECT_FILE
    assert meta.filename == "manual.pdf"
    assert meta.total_bytes == 4096
    assert meta.supports_resume is True


def test_resolver_attempts_generic_extraction_for_html_and_rejects_plain_html() -> None:
    def html_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"})

    direct = DirectHttpEngine(transport=httpx.MockTransport(html_handler))

    # Plain webpage without media -> HtmlNotMediaError
    fake_yt_fail = _FakeYtDlpEngine(specialized_hosts=set(), generic_success=False)
    resolver_fail = UrlCapabilityResolver(ytdlp_engine=fake_yt_fail, direct_engine=direct)
    with pytest.raises(HtmlNotMediaError):
        resolver_fail.resolve("https://blog.example.com/article")

    # Webpage with embedded generic media -> EngineType.YTDLP generic page
    fake_yt_ok = _FakeYtDlpEngine(specialized_hosts=set(), generic_success=True)
    resolver_ok = UrlCapabilityResolver(ytdlp_engine=fake_yt_ok, direct_engine=direct)
    meta = resolver_ok.resolve("https://media.example.com/embedded")
    assert meta.engine_type == EngineType.YTDLP
    assert meta.resource_kind == ResourceKind.GENERIC_MEDIA_PAGE
