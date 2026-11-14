"""Integration tests for YtDlpEngine using controlled fixtures and mocked YoutubeDL."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
import yt_dlp
from yt_dlp.utils import ExtractorError

from link_downloader.core.enums import DownloadStatus, EngineType, FormatKind, ResourceKind
from link_downloader.core.exceptions import (
    DependencyMissingError,
    DownloadCancelledError,
    DownloadPausedError,
    ExtractionError,
)
from link_downloader.core.models import (
    DownloadJob,
    DownloadProgress,
    DownloadRequest,
    FormatOption,
)
from link_downloader.engines.ytdlp_engine import YtDlpEngine
from link_downloader.services.dependency_service import DependencyService
from link_downloader.services.ffmpeg_service import FfmpegService
from tests.fixtures.sample_metadata import SAMPLE_PLAYLIST_INFO, SAMPLE_YOUTUBE_INFO


class _FakeFfmpegService(FfmpegService):
    def __init__(self, ffmpeg_path: str | None) -> None:
        super().__init__()
        self._path = ffmpeg_path

    def find_ffmpeg(self) -> str | None:
        return self._path


class _FakeDependencyService(DependencyService):
    def __init__(self, ffmpeg_svc: FfmpegService, runtimes: dict[str, dict[str, str]]) -> None:
        super().__init__(ffmpeg_svc)
        self._runtimes = runtimes

    def get_ytdlp_js_runtimes(self) -> dict[str, dict[str, str]]:
        return self._runtimes


def test_probe_extracts_accurate_formats_without_inventing_resolutions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_opts: list[dict[str, Any]] = []

    class FakeYoutubeDL:
        def __init__(self, opts: dict[str, Any]) -> None:
            captured_opts.append(opts)

        def __enter__(self) -> FakeYoutubeDL:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
            assert download is False
            return SAMPLE_YOUTUBE_INFO

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    ffmpeg_svc = _FakeFfmpegService("/usr/bin/ffmpeg")
    dep_svc = _FakeDependencyService(ffmpeg_svc, {"node": {"path": "/usr/bin/node"}})
    engine = YtDlpEngine(ffmpeg_service=ffmpeg_svc, dependency_service=dep_svc)

    meta = engine.probe("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert meta.engine_type is EngineType.YTDLP
    assert meta.resource_kind is ResourceKind.VIDEO_PLATFORM
    assert meta.title == "Sample Cross-Platform Demo Video"
    assert meta.uploader == "Demo Channel"
    assert meta.duration_seconds == 212
    assert meta.source_platform == "Youtube"

    # SAMPLE_YOUTUBE_INFO provides 360p, 720p, 1080p only — never 1440p or 2160p
    resolutions = {f.resolution for f in meta.formats}
    assert "1080p" in resolutions
    assert "720p" in resolutions
    assert "360p" in resolutions
    assert "1440p" not in resolutions
    assert "2160p" not in resolutions
    assert any(f.convert_to_mp3 for f in meta.formats)
    assert isinstance(captured_opts[0].get("js_runtimes"), dict)
    assert "node" in captured_opts[0]["js_runtimes"]


def test_probe_playlist_populates_playlist_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeYoutubeDL:
        def __init__(self, opts: dict[str, Any]) -> None:
            self.opts = opts

        def __enter__(self) -> FakeYoutubeDL:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
            return SAMPLE_PLAYLIST_INFO

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    engine = YtDlpEngine(ffmpeg_service=_FakeFfmpegService("/usr/bin/ffmpeg"))
    meta = engine.probe("https://www.youtube.com/playlist?list=PL12345")

    assert meta.is_playlist is True
    assert meta.playlist_count == 2
    assert meta.resource_kind is ResourceKind.PLAYLIST


def test_download_requires_ffmpeg_when_merging_or_converting_mp3(tmp_path: Path) -> None:
    ffmpeg_svc = _FakeFfmpegService(None)
    engine = YtDlpEngine(ffmpeg_service=ffmpeg_svc)

    merged_fmt = FormatOption(
        format_id="137+140",
        ext="mp4",
        kind=FormatKind.VIDEO_AUDIO,
        resolution="1080p",
        requires_ffmpeg=True,
    )
    job = DownloadJob(
        job_id="job-no-ffmpeg",
        request=DownloadRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            destination_dir=tmp_path,
            selected_format=merged_fmt,
        ),
        title="Sample Video",
        platform="Youtube",
        engine_type=EngineType.YTDLP,
        format_id="137+140",
        format_label="1080p",
    )

    with pytest.raises(DependencyMissingError, match="FFmpeg is required"):
        engine.download(job, lambda _p: None, threading.Event(), threading.Event())


def test_download_emits_progress_postprocessor_and_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeYoutubeDL:
        def __init__(self, opts: dict[str, Any]) -> None:
            self.opts = opts

        def __enter__(self) -> FakeYoutubeDL:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def download(self, urls: list[str]) -> int:
            out_template = Path(self.opts["outtmpl"])
            final_file = out_template.with_name(out_template.name.replace("%(ext)s", "mp4"))
            final_file.parent.mkdir(parents=True, exist_ok=True)

            for hook in self.opts["progress_hooks"]:
                hook(
                    {
                        "status": "downloading",
                        "downloaded_bytes": 512_000,
                        "total_bytes": 1_024_000,
                        "speed": 256_000.0,
                        "eta": 2,
                        "filename": str(final_file),
                        "tmpfilename": f"{final_file}.part",
                    }
                )
            final_file.write_bytes(b"fake-mp4-stream-payload")
            for hook in self.opts["progress_hooks"]:
                hook(
                    {
                        "status": "finished",
                        "downloaded_bytes": 1_024_000,
                        "total_bytes": 1_024_000,
                        "filename": str(final_file),
                    }
                )
            for pp_hook in self.opts["postprocessor_hooks"]:
                pp_hook(
                    {
                        "status": "started",
                        "postprocessor": "Merger",
                        "info_dict": {"filepath": str(final_file)},
                    }
                )
            return 0

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    engine = YtDlpEngine(ffmpeg_service=_FakeFfmpegService("/usr/bin/ffmpeg"))
    fmt = FormatOption(
        format_id="18",
        ext="mp4",
        kind=FormatKind.VIDEO_AUDIO,
        resolution="360p",
    )
    job = DownloadJob(
        job_id="job-yt-ok",
        request=DownloadRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            destination_dir=tmp_path,
            selected_format=fmt,
            preferred_filename="Sample Demo",
        ),
        title="Sample Demo",
        platform="Youtube",
        engine_type=EngineType.YTDLP,
        format_id="18",
        format_label="360p MP4",
    )

    events: list[DownloadProgress] = []
    result_path = engine.download(job, events.append, threading.Event(), threading.Event())

    assert result_path.exists()
    assert result_path.read_bytes() == b"fake-mp4-stream-payload"
    statuses = [ev.status for ev in events]
    assert DownloadStatus.DOWNLOADING in statuses
    assert DownloadStatus.PROCESSING in statuses
    assert statuses[-1] is DownloadStatus.COMPLETED


def test_download_cancel_cleans_up_part_and_ytdl_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cancel_event = threading.Event()
    part_path_holder: list[Path] = []
    ytdl_path_holder: list[Path] = []

    class FakeYoutubeDL:
        def __init__(self, opts: dict[str, Any]) -> None:
            self.opts = opts

        def __enter__(self) -> FakeYoutubeDL:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def download(self, urls: list[str]) -> int:
            out_template = Path(self.opts["outtmpl"])
            base_file = out_template.with_name(out_template.name.replace("%(ext)s", "mp4"))
            part_file = Path(f"{base_file}.part")
            ytdl_file = Path(f"{base_file}.ytdl")
            part_file.write_bytes(b"partial")
            ytdl_file.write_bytes(b"meta")
            part_path_holder.append(part_file)
            ytdl_path_holder.append(ytdl_file)

            cancel_event.set()
            for hook in self.opts["progress_hooks"]:
                hook(
                    {
                        "status": "downloading",
                        "downloaded_bytes": 100,
                        "total_bytes": 1000,
                        "filename": str(base_file),
                        "tmpfilename": str(base_file),
                    }
                )
            return 0

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    engine = YtDlpEngine(ffmpeg_service=_FakeFfmpegService("/usr/bin/ffmpeg"))
    job = DownloadJob(
        job_id="job-yt-cancel",
        request=DownloadRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            destination_dir=tmp_path,
        ),
        title="Cancelled Clip",
        platform="Youtube",
        engine_type=EngineType.YTDLP,
        format_id="18",
        format_label="360p",
    )

    with pytest.raises(DownloadCancelledError):
        engine.download(job, lambda _p: None, cancel_event, threading.Event())

    assert not part_path_holder[0].exists()
    assert not ytdl_path_holder[0].exists()


def test_download_pause_preserves_part_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pause_event = threading.Event()
    part_path_holder: list[Path] = []

    class FakeYoutubeDL:
        def __init__(self, opts: dict[str, Any]) -> None:
            self.opts = opts

        def __enter__(self) -> FakeYoutubeDL:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def download(self, urls: list[str]) -> int:
            out_template = Path(self.opts["outtmpl"])
            base_file = out_template.with_name(out_template.name.replace("%(ext)s", "mp4"))
            part_file = Path(f"{base_file}.part")
            part_file.write_bytes(b"resumable-part")
            part_path_holder.append(part_file)

            pause_event.set()
            for hook in self.opts["progress_hooks"]:
                hook(
                    {
                        "status": "downloading",
                        "downloaded_bytes": 256,
                        "total_bytes": 1024,
                        "filename": str(base_file),
                        "tmpfilename": str(base_file),
                    }
                )
            return 0

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    engine = YtDlpEngine(ffmpeg_service=_FakeFfmpegService("/usr/bin/ffmpeg"))
    job = DownloadJob(
        job_id="job-yt-pause",
        request=DownloadRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            destination_dir=tmp_path,
        ),
        title="Paused Clip",
        platform="Youtube",
        engine_type=EngineType.YTDLP,
        format_id="18",
        format_label="360p",
    )

    with pytest.raises(DownloadPausedError):
        engine.download(job, lambda _p: None, threading.Event(), pause_event)

    assert part_path_holder[0].exists()


def test_extractor_error_maps_to_friendly_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeYoutubeDL:
        def __init__(self, opts: dict[str, Any]) -> None:
            self.opts = opts

        def __enter__(self) -> FakeYoutubeDL:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
            raise ExtractorError("ERROR: Private video. Sign in if you've been granted access")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    engine = YtDlpEngine(ffmpeg_service=_FakeFfmpegService("/usr/bin/ffmpeg"))
    with pytest.raises(ExtractionError, match="private"):
        engine.probe("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
