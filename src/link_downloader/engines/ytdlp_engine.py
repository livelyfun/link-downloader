"""yt-dlp Python API engine for metadata extraction, format listing, and media downloading."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yt_dlp
from yt_dlp.extractor import gen_extractor_classes
from yt_dlp.utils import DownloadCancelled, DownloadError, ExtractorError

from link_downloader.core.enums import DownloadStatus, EngineType, FormatKind, ResourceKind
from link_downloader.core.exceptions import (
    DependencyMissingError,
    DownloadCancelledError,
    DownloadPausedError,
    ExtractionError,
    UnsupportedResourceError,
)
from link_downloader.core.models import (
    DownloadJob,
    DownloadProgress,
    FormatOption,
    ResourceMetadata,
)
from link_downloader.core.validators import normalize_and_validate_url
from link_downloader.engines.base import BaseDownloadEngine, ProgressCallback
from link_downloader.services.dependency_service import DependencyService
from link_downloader.services.ffmpeg_service import FfmpegService
from link_downloader.services.file_service import resolve_collision_safe_path, sanitize_filename

logger = logging.getLogger(__name__)

_AUDIO_EXTRACTORS = frozenset(
    {"soundcloud", "bandcamp", "mixcloud", "spotify", "audiomack", "hearthisat"}
)


class _SilentYtdlpLogger:
    """Routes yt-dlp internal messages to Python logging without touching stdout/stderr."""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug]"):
            logger.debug("yt-dlp: %s", msg)

    def info(self, msg: str) -> None:
        logger.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.warning("yt-dlp warning: %s", msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        logger.error("yt-dlp error: %s", msg)


def _friendly_ytdlp_error(raw_message: str) -> str:
    msg = raw_message.strip()
    lower = msg.lower()
    if "private video" in lower:
        return "This video is private and cannot be downloaded without authorization."
    if "video unavailable" in lower or "this video is not available" in lower:
        return "This media item is unavailable or has been removed."
    if "sign in" in lower or "login" in lower or "cookies" in lower:
        return "This content requires authentication and cannot be extracted automatically."
    if "age" in lower and ("confirm" in lower or "restricted" in lower):
        return "This content is age-restricted by the source platform."
    if "unsupported url" in lower:
        return "No supported media streams were found at this URL."
    if "ffmpeg" in lower and ("not installed" in lower or "not found" in lower):
        return "FFmpeg is required for merging or converting this format, but was not found."
    if "http error 429" in lower or "too many requests" in lower:
        return "The source platform temporarily rate-limited requests (HTTP 429). Try again later."
    if "timed out" in lower:
        return "The request timed out while communicating with the media host."
    first_line = msg.splitlines()[0] if msg else "Media extraction failed."
    return first_line.removeprefix("ERROR:").strip()


class YtDlpEngine(BaseDownloadEngine):
    """Media platform extraction and download engine backed by yt_dlp.YoutubeDL."""

    def __init__(
        self,
        *,
        ffmpeg_service: FfmpegService | None = None,
        dependency_service: DependencyService | None = None,
        allow_private: bool = False,
        prefer_ipv4: bool = True,
    ) -> None:
        self._ffmpeg = ffmpeg_service or FfmpegService()
        self._deps = dependency_service or DependencyService(self._ffmpeg)
        self._allow_private = allow_private
        self._prefer_ipv4 = prefer_ipv4
        self._extractors_cache: list[Any] | None = None

    def _get_extractors(self) -> list[Any]:
        if self._extractors_cache is None:
            self._extractors_cache = [
                ie_cls
                for ie_cls in gen_extractor_classes()
                if ie_cls.ie_key().lower() != "generic"
            ]
        return self._extractors_cache

    def is_specialized_url(self, url: str) -> tuple[bool, str | None]:
        """Return (True, extractor_name) if a non-generic yt-dlp extractor handles this URL."""
        for ie_cls in self._get_extractors():
            try:
                if ie_cls.suitable(url):
                    return True, str(ie_cls.ie_key())
            except Exception:
                continue
        return False, None

    def _build_base_opts(self, *, ytdlp_logger: _SilentYtdlpLogger) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": False,
            "noprogress": True,
            "color": "never",
            "logger": ytdlp_logger,
            "socket_timeout": 20,
            "retries": 3,
            "fragment_retries": 3,
            "windowsfilenames": True,
        }
        ffmpeg_path = self._ffmpeg.find_ffmpeg()
        if ffmpeg_path:
            opts["ffmpeg_location"] = ffmpeg_path

        js_runtimes = self._deps.get_ytdlp_js_runtimes()
        if js_runtimes:
            opts["js_runtimes"] = js_runtimes

        if self._prefer_ipv4:
            opts["source_address"] = "0.0.0.0"

        return opts

    def _build_format_options(
        self,
        raw_formats: list[dict[str, Any]],
        *,
        ffmpeg_available: bool,
        fallback_ext: str | None = None,
    ) -> list[FormatOption]:
        """Build accurate FormatOption entries strictly from formats actually reported by source."""
        parsed: list[FormatOption] = []
        seen_ids: set[str] = set()
        available_heights: set[int] = set()
        has_video_only = False
        has_audio = False

        for fmt in raw_formats:
            fmt_id = str(fmt.get("format_id") or "").strip()
            ext = str(fmt.get("ext") or fallback_ext or "mp4").lower()
            if not fmt_id or ext in {"mhtml", "html"}:
                continue

            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")
            has_v = bool(vcodec and vcodec != "none")
            has_a = bool(acodec and acodec != "none")

            # Some extractors omit vcodec/acodec on single-file entries; treat non-audio ext as combined
            if vcodec is None and acodec is None:
                if ext in {"mp3", "m4a", "aac", "ogg", "opus", "wav", "flac", "weba"}:
                    has_v, has_a = False, True
                else:
                    has_v, has_a = True, True

            if not has_v and not has_a:
                continue

            if has_v and has_a:
                kind = FormatKind.VIDEO_AUDIO
            elif has_v:
                kind = FormatKind.VIDEO_ONLY
                has_video_only = True
            else:
                kind = FormatKind.AUDIO_ONLY
                has_audio = True

            if has_a:
                has_audio = True

            height = fmt.get("height")
            width = fmt.get("width")
            if isinstance(height, int) and height > 0 and has_v:
                available_heights.add(height)

            abr = fmt.get("abr")
            if has_v:
                res_label = f"{height}p" if height else str(fmt.get("resolution") or "Video")
            else:
                res_label = f"{round(abr)} kbps" if abr else "Audio"

            opt = FormatOption(
                format_id=fmt_id,
                ext=ext,
                kind=kind,
                resolution=res_label,
                height=height if isinstance(height, int) else None,
                width=width if isinstance(width, int) else None,
                fps=float(fmt["fps"]) if fmt.get("fps") is not None else None,
                vcodec=str(vcodec) if has_v and vcodec else None,
                acodec=str(acodec) if has_a and acodec else None,
                filesize_bytes=fmt.get("filesize"),
                filesize_approx_bytes=fmt.get("filesize_approx"),
                tbr=float(fmt["tbr"]) if fmt.get("tbr") is not None else None,
                abr=float(abr) if abr is not None else None,
                vbr=float(fmt["vbr"]) if fmt.get("vbr") is not None else None,
                requires_ffmpeg=False,
                note=str(fmt.get("format_note") or ""),
            )
            opt.label = (
                f"{res_label} · {ext.upper()} · {opt.codec_summary} · {opt.display_size}"
            )
            if fmt_id not in seen_ids:
                parsed.append(opt)
                seen_ids.add(fmt_id)

        # Sort individual streams cleanly
        kind_rank = {
            FormatKind.VIDEO_AUDIO: 0,
            FormatKind.VIDEO_ONLY: 1,
            FormatKind.AUDIO_ONLY: 2,
            FormatKind.DIRECT: 3,
        }
        parsed.sort(
            key=lambda f: (
                kind_rank.get(f.kind, 9),
                -(f.height or 0),
                -(f.abr or 0.0),
                -(f.tbr or 0.0),
            )
        )

        # Build smart preset options ONLY for resolutions actually available in raw_formats
        presets: list[FormatOption] = []
        if available_heights:
            best_height = max(available_heights)
            needs_merge = has_video_only and has_audio
            best_fmt_id = "bestvideo+bestaudio/best" if needs_merge else "best"
            ffmpeg_note = (
                "Requires FFmpeg to merge streams"
                if (needs_merge and not ffmpeg_available)
                else ("Auto-merges best video + audio" if needs_merge else "Best available combined stream")
            )
            presets.append(
                FormatOption(
                    format_id=best_fmt_id,
                    ext="mp4" if needs_merge else (fallback_ext or "mp4"),
                    kind=FormatKind.VIDEO_AUDIO,
                    resolution=f"Best ({best_height}p)",
                    height=best_height,
                    vcodec="best",
                    acodec="best" if has_audio else None,
                    requires_ffmpeg=needs_merge,
                    is_auto_merged=needs_merge,
                    label=f"Best Available ({best_height}p) · {'MP4 (Auto-Merge)' if needs_merge else 'Best'}",
                    note=ffmpeg_note,
                )
            )

            # Offer clean resolution-capped merged options ONLY for heights actually present
            for h in sorted(available_heights, reverse=True):
                if h == best_height and len(available_heights) > 1:
                    continue
                preset_id = (
                    f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"
                    if (has_video_only and has_audio)
                    else f"best[height<={h}]"
                )
                if preset_id in seen_ids:
                    continue
                # Find representative size estimate if available
                matching_v = [f for f in parsed if f.height == h and f.kind != FormatKind.AUDIO_ONLY]
                rep_size = matching_v[0].effective_size_bytes if matching_v else None
                presets.append(
                    FormatOption(
                        format_id=preset_id,
                        ext="mp4",
                        kind=FormatKind.VIDEO_AUDIO,
                        resolution=f"{h}p",
                        height=h,
                        vcodec=matching_v[0].vcodec if matching_v else None,
                        acodec="bestaudio" if (has_video_only and has_audio) else None,
                        filesize_approx_bytes=rep_size,
                        requires_ffmpeg=has_video_only and has_audio,
                        is_auto_merged=has_video_only and has_audio,
                        label=f"{h}p · MP4{' (Merged)' if (has_video_only and has_audio) else ''}",
                        note="Requires FFmpeg" if (has_video_only and has_audio and not ffmpeg_available) else "",
                    )
                )

        if has_audio:
            presets.append(
                FormatOption(
                    format_id="bestaudio/best",
                    ext="mp3",
                    kind=FormatKind.AUDIO_ONLY,
                    resolution="Best Audio",
                    acodec="mp3",
                    requires_ffmpeg=True,
                    convert_to_mp3=True,
                    label="Audio Only · MP3 (FFmpeg Conversion)",
                    note="Requires FFmpeg" if not ffmpeg_available else "Converts best audio stream to MP3",
                )
            )
            presets.append(
                FormatOption(
                    format_id="bestaudio[ext=m4a]/bestaudio/best",
                    ext="m4a",
                    kind=FormatKind.AUDIO_ONLY,
                    resolution="Best Native Audio",
                    acodec="aac/opus",
                    requires_ffmpeg=False,
                    label="Audio Only · Native Best (M4A/Opus)",
                    note="Downloads native audio stream without re-encoding",
                )
            )

        # Combine smart presets + raw formats without duplicating IDs
        combined: list[FormatOption] = []
        used_ids: set[str] = set()
        for item in [*presets, *parsed]:
            if item.format_id not in used_ids:
                combined.append(item)
                used_ids.add(item.format_id)

        return combined

    def probe(
        self,
        url: str,
        *,
        allow_playlist: bool = False,
        generic_mode: bool = False,
    ) -> ResourceMetadata:
        """Extract metadata and available formats using yt_dlp.YoutubeDL without downloading."""
        normalized = normalize_and_validate_url(
            url,
            allow_private=self._allow_private,
            strict_dns=False,
        )
        ytdlp_logger = _SilentYtdlpLogger()
        opts = self._build_base_opts(ytdlp_logger=ytdlp_logger)
        opts["noplaylist"] = not allow_playlist
        if allow_playlist:
            opts["extract_flat"] = "in_playlist"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(normalized, download=False)
        except (DownloadError, ExtractorError) as exc:
            friendly = _friendly_ytdlp_error(str(exc))
            if generic_mode:
                raise UnsupportedResourceError(friendly, details=str(exc)) from exc
            raise ExtractionError(friendly, details=str(exc)) from exc
        except Exception as exc:
            raise ExtractionError(f"Unexpected yt-dlp error: {exc}", details=str(exc)) from exc

        if not isinstance(info, dict):
            raise UnsupportedResourceError("Could not extract valid media metadata from URL.")

        is_playlist = info.get("_type") == "playlist"
        playlist_count: int | None = None
        target_info = info
        if is_playlist:
            entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
            playlist_count = info.get("playlist_count") or len(entries)
            if not entries:
                raise UnsupportedResourceError("This playlist contains no downloadable entries.")
            if not entries[0].get("formats") and entries[0].get("url"):
                # Re-extract first item fully when flat-extracted so real formats are shown
                try:
                    with yt_dlp.YoutubeDL({**opts, "extract_flat": False, "noplaylist": True}) as ydl:
                        first_full = ydl.extract_info(entries[0]["url"], download=False)
                        if isinstance(first_full, dict):
                            target_info = first_full
                except Exception:
                    target_info = entries[0]
            else:
                target_info = entries[0]

        raw_formats = list(target_info.get("formats") or [])
        if not raw_formats and target_info.get("url") and target_info.get("ext") not in {"html", "mhtml", None}:
            raw_formats = [
                {
                    "format_id": str(target_info.get("format_id") or "best"),
                    "ext": str(target_info.get("ext") or "mp4"),
                    "vcodec": target_info.get("vcodec"),
                    "acodec": target_info.get("acodec"),
                    "height": target_info.get("height"),
                    "width": target_info.get("width"),
                    "filesize": target_info.get("filesize"),
                    "filesize_approx": target_info.get("filesize_approx"),
                    "tbr": target_info.get("tbr"),
                    "abr": target_info.get("abr"),
                }
            ]

        ffmpeg_available = self._ffmpeg.is_ffmpeg_available()
        formats = self._build_format_options(
            raw_formats,
            ffmpeg_available=ffmpeg_available,
            fallback_ext=target_info.get("ext"),
        )
        if not formats:
            raise UnsupportedResourceError(
                "No downloadable video or audio streams were found at this URL.",
            )

        extractor_name = str(
            info.get("extractor_key") or info.get("extractor") or target_info.get("extractor") or "media"
        )
        extractor_lower = extractor_name.lower()
        if extractor_lower == "generic":
            resource_kind = ResourceKind.GENERIC_MEDIA_PAGE
        elif is_playlist:
            resource_kind = ResourceKind.PLAYLIST
        elif extractor_lower in _AUDIO_EXTRACTORS:
            resource_kind = ResourceKind.AUDIO_PLATFORM
        else:
            resource_kind = ResourceKind.VIDEO_PLATFORM

        title = str(info.get("title") or target_info.get("title") or "Untitled Media").strip()
        hostname = urlsplit(normalized).hostname or extractor_lower
        platform_label = (
            "Webpage Media"
            if extractor_lower == "generic"
            else str(info.get("extractor_key") or extractor_name)
        )

        return ResourceMetadata(
            url=url,
            normalized_url=normalized,
            engine_type=EngineType.YTDLP,
            resource_kind=resource_kind,
            title=title,
            source_platform=platform_label,
            hostname=hostname,
            uploader=info.get("uploader") or target_info.get("uploader") or info.get("channel"),
            duration_seconds=target_info.get("duration") or info.get("duration"),
            description=target_info.get("description") or info.get("description"),
            thumbnail_url=target_info.get("thumbnail") or info.get("thumbnail"),
            view_count=target_info.get("view_count"),
            upload_date=target_info.get("upload_date"),
            formats=formats,
            is_playlist=is_playlist,
            playlist_count=playlist_count,
            extractor_name=extractor_name,
            warnings=ytdlp_logger.warnings,
        )

    def download(
        self,
        job: DownloadJob,
        progress_callback: ProgressCallback,
        cancel_event: threading.Event,
        pause_event: threading.Event,
    ) -> Path:
        """Download and optionally merge/convert media via yt_dlp.YoutubeDL hooks."""
        if cancel_event.is_set():
            raise DownloadCancelledError("Download cancelled before starting.")

        req = job.request
        fmt = req.selected_format
        format_id = fmt.format_id if fmt else (job.format_id or "bestvideo+bestaudio/best")
        needs_mp3 = bool((fmt and fmt.convert_to_mp3) or req.auto_convert_mp3)
        needs_merge = ("+" in format_id) or bool(fmt and fmt.requires_ffmpeg)

        ffmpeg_path = self._ffmpeg.find_ffmpeg()
        if (needs_mp3 or needs_merge) and not ffmpeg_path:
            raise DependencyMissingError(
                "FFmpeg is required to merge video/audio streams or convert audio to MP3. "
                "Please install FFmpeg or select a combined pre-merged format.",
            )

        dest_dir = Path(req.destination_dir).expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        base_title = sanitize_filename(req.preferred_filename or job.title or "media")
        base_stem = Path(base_title).stem if Path(base_title).suffix else base_title
        expected_ext = "mp3" if needs_mp3 else (fmt.ext if fmt and fmt.ext else "mp4")
        resolved_target = job.reserved_path or resolve_collision_safe_path(
            dest_dir,
            f"{base_stem}.{expected_ext}",
            req.overwrite_behavior,
        )
        target_stem = resolved_target.stem

        ytdlp_logger = _SilentYtdlpLogger()
        opts = self._build_base_opts(ytdlp_logger=ytdlp_logger)
        opts["format"] = format_id
        opts["outtmpl"] = str(dest_dir / f"{target_stem}.%(ext)s")
        opts["continuedl"] = True
        opts["nopart"] = False
        opts["noplaylist"] = not req.allow_playlist
        if not req.allow_playlist:
            opts["playlist_items"] = "1"
        if "+" in format_id and not needs_mp3:
            opts["merge_output_format"] = "mp4"

        if needs_mp3:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }
            ]

        observed_files: list[Path] = []
        temp_files: set[Path] = set()
        last_emit = 0.0

        def _progress_hook(d: dict[str, Any]) -> None:
            nonlocal last_emit
            if tmp := d.get("tmpfilename"):
                temp_files.add(Path(tmp))
            if fn := d.get("filename"):
                observed_files.append(Path(fn))

            if cancel_event.is_set():
                raise DownloadCancelledError("Download cancelled.")
            if pause_event.is_set():
                raise DownloadPausedError("Download paused.")

            status = d.get("status")
            if status == "downloading":
                now = time.monotonic()
                if now - last_emit < 0.12:
                    return
                last_emit = now

                downloaded = int(d.get("downloaded_bytes") or 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                total_int = int(total) if total else None
                pct = (
                    min(100.0, downloaded / total_int * 100.0)
                    if total_int and total_int > 0
                    else None
                )
                speed = float(d["speed"]) if d.get("speed") is not None else None
                eta = int(d["eta"]) if d.get("eta") is not None else None
                filename = Path(str(d.get("filename") or resolved_target.name)).name

                progress_callback(
                    DownloadProgress(
                        job_id=job.job_id,
                        status=DownloadStatus.DOWNLOADING,
                        percent=pct,
                        downloaded_bytes=downloaded,
                        total_bytes=total_int,
                        speed_bps=speed,
                        eta_seconds=eta,
                        filename=filename,
                        destination_path=str(resolved_target),
                        supports_pause=True,
                        supports_resume=True,
                    )
                )
            elif status == "finished":
                fn = str(d.get("filename") or resolved_target.name)
                downloaded = int(d.get("downloaded_bytes") or d.get("total_bytes") or 0)
                progress_callback(
                    DownloadProgress(
                        job_id=job.job_id,
                        status=DownloadStatus.PROCESSING,
                        percent=100.0,
                        downloaded_bytes=downloaded,
                        total_bytes=downloaded or None,
                        speed_bps=None,
                        eta_seconds=0,
                        filename=Path(fn).name,
                        destination_path=fn,
                        message="Finalizing media stream...",
                        supports_pause=False,
                        supports_resume=False,
                    )
                )

        def _postprocessor_hook(d: dict[str, Any]) -> None:
            if cancel_event.is_set():
                raise DownloadCancelledError("Download cancelled during post-processing.")
            info_dict = d.get("info_dict") or {}
            filepath = info_dict.get("filepath") or info_dict.get("_filename")
            if filepath:
                observed_files.append(Path(str(filepath)))
            if d.get("status") == "started":
                progress_callback(
                    DownloadProgress(
                        job_id=job.job_id,
                        status=DownloadStatus.PROCESSING,
                        percent=None,
                        filename=resolved_target.name,
                        destination_path=str(filepath or resolved_target),
                        message=f"Processing ({d.get('postprocessor', 'FFmpeg')})...",
                        supports_pause=False,
                        supports_resume=False,
                    )
                )

        opts["progress_hooks"] = [_progress_hook]
        opts["postprocessor_hooks"] = [_postprocessor_hook]

        def _cleanup_temps() -> None:
            for path in list(temp_files):
                for suffix_candidate in (path, Path(f"{path}.part"), Path(f"{path}.ytdl")):
                    try:
                        if suffix_candidate.exists() and suffix_candidate.is_file():
                            suffix_candidate.unlink()
                    except OSError:
                        pass

        job.can_pause = True
        job.can_resume = True

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([req.url])
        except DownloadCancelledError:
            _cleanup_temps()
            raise
        except DownloadPausedError:
            # Keep .part files intact so continuedl=True can resume
            raise
        except DownloadCancelled as exc:
            _cleanup_temps()
            raise DownloadCancelledError("Download cancelled.") from exc
        except (DownloadError, ExtractorError) as exc:
            if cancel_event.is_set():
                _cleanup_temps()
                raise DownloadCancelledError("Download cancelled.") from exc
            if pause_event.is_set():
                raise DownloadPausedError("Download paused.") from exc
            raise ExtractionError(_friendly_ytdlp_error(str(exc)), details=str(exc)) from exc
        except Exception as exc:
            if cancel_event.is_set():
                _cleanup_temps()
                raise DownloadCancelledError("Download cancelled.") from exc
            raise ExtractionError(f"Media download failed: {exc}", details=str(exc)) from exc

        if cancel_event.is_set():
            _cleanup_temps()
            raise DownloadCancelledError("Download cancelled.")

        final_path = self._locate_output_file(dest_dir, target_stem, expected_ext, observed_files)
        if final_path is None:
            raise ExtractionError("Download finished, but the output media file could not be located.")

        file_size = final_path.stat().st_size if final_path.exists() else None
        progress_callback(
            DownloadProgress(
                job_id=job.job_id,
                status=DownloadStatus.COMPLETED,
                percent=100.0,
                downloaded_bytes=file_size or 0,
                total_bytes=file_size,
                speed_bps=None,
                eta_seconds=0,
                filename=final_path.name,
                destination_path=str(final_path),
                supports_pause=False,
                supports_resume=False,
            )
        )
        return final_path

    @staticmethod
    def _locate_output_file(
        dest_dir: Path,
        target_stem: str,
        expected_ext: str,
        observed_files: list[Path],
    ) -> Path | None:
        preferred = dest_dir / f"{target_stem}.{expected_ext}"
        if preferred.is_file():
            return preferred

        for candidate in reversed(observed_files):
            if candidate.is_file() and candidate.suffix not in {".part", ".ytdl"}:
                return candidate
            mp3_variant = candidate.with_suffix(f".{expected_ext}")
            if mp3_variant.is_file():
                return mp3_variant

        matches = [
            p
            for p in dest_dir.glob(f"{target_stem}.*")
            if p.is_file() and p.suffix not in {".part", ".ytdl"}
        ]
        if matches:
            matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return matches[0]
        return None
