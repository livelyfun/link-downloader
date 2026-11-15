"""FFmpeg and FFprobe discovery, version probing, and one-click static installation."""

from __future__ import annotations

import contextlib
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx

from link_downloader.platform.paths import get_assets_dir, get_managed_bin_dir

logger = logging.getLogger(__name__)
_VERSION_RE = re.compile(r"(?:ffmpeg|ffprobe)\s+version\s+(\S+)", re.IGNORECASE)
_TARGET_BINARIES = {"ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe"}


def get_ffmpeg_download_targets(
    sys_platform: str | None = None,
    machine: str | None = None,
) -> list[tuple[str, str]]:
    """Return verified static FFmpeg archive `(archive_type, url)` targets for a platform."""
    plat = (sys_platform or sys.platform).lower()
    raw_arch = (machine or platform.machine()).lower()
    if raw_arch in {"x86_64", "amd64"}:
        arch = "x86_64"
    elif raw_arch in {"arm64", "aarch64"}:
        arch = "arm64"
    else:
        arch = raw_arch

    if plat.startswith("linux"):
        if arch == "x86_64":
            return [
                (
                    "tar.xz",
                    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
                )
            ]
        if arch == "arm64":
            return [
                (
                    "tar.xz",
                    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
                )
            ]
    elif plat == "win32" or plat.startswith("win"):
        if arch == "x86_64":
            return [
                (
                    "zip",
                    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
                )
            ]
        if arch == "arm64":
            return [
                (
                    "zip",
                    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-winarm64-gpl.zip",
                )
            ]
    elif plat == "darwin":
        if arch == "arm64":
            return [
                ("zip", "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/snapshot/ffmpeg.zip"),
                ("zip", "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/snapshot/ffprobe.zip"),
            ]
        if arch == "x86_64":
            return [
                ("zip", "https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffmpeg.zip"),
                ("zip", "https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffprobe.zip"),
            ]

    raise RuntimeError(
        f"Automatic FFmpeg download is not available for this system ({plat} / {arch})."
    )


class FfmpegService:
    """Locates, verifies, and installs FFmpeg/FFprobe binaries without shell execution."""

    def __init__(self, custom_ffmpeg_path: str | None = None) -> None:
        self._custom_ffmpeg_path = custom_ffmpeg_path

    def _candidate_paths(self, binary_name: str) -> list[Path]:
        exe_name = f"{binary_name}.exe" if sys.platform == "win32" else binary_name
        candidates: list[Path] = []

        if self._custom_ffmpeg_path and binary_name == "ffmpeg":
            candidates.append(Path(self._custom_ffmpeg_path).expanduser())

        # Bundled binary locations (if ever packaged alongside the app)
        assets_bin = get_assets_dir() / "bin" / exe_name
        candidates.append(assets_bin)

        # App-managed user data binary folder (installed via one-click Download FFmpeg)
        with contextlib.suppress(OSError):
            candidates.append(get_managed_bin_dir() / exe_name)

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.append(exe_dir / exe_name)
            candidates.append(exe_dir / "bin" / exe_name)

        which_hit = shutil.which(exe_name) or shutil.which(binary_name)
        if which_hit:
            candidates.append(Path(which_hit))

        home = Path.home()
        if sys.platform == "win32":
            candidates.extend(
                [
                    Path("C:/ffmpeg/bin") / exe_name,
                    Path("C:/Program Files/ffmpeg/bin") / exe_name,
                    home / "scoop" / "shims" / exe_name,
                    Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / exe_name,
                ]
            )
        elif sys.platform == "darwin":
            candidates.extend(
                [
                    Path("/opt/homebrew/bin") / exe_name,
                    Path("/usr/local/bin") / exe_name,
                    home / ".local" / "bin" / exe_name,
                ]
            )
        else:
            candidates.extend(
                [
                    home / ".local" / "bin" / exe_name,
                    Path("/usr/local/bin") / exe_name,
                    Path("/usr/bin") / exe_name,
                    Path("/snap/bin") / exe_name,
                ]
            )

        return candidates

    def find_binary(self, binary_name: str) -> str | None:
        """Return the resolved path to ffmpeg or ffprobe, or None if not found."""
        for candidate in self._candidate_paths(binary_name):
            try:
                if candidate.is_file():
                    return str(candidate.resolve())
            except OSError:
                continue
        return None

    def find_ffmpeg(self) -> str | None:
        return self.find_binary("ffmpeg")

    def find_ffprobe(self) -> str | None:
        return self.find_binary("ffprobe")

    def get_version(self, binary_path: str | None) -> str | None:
        """Run `<binary> -version` safely without a shell and parse the version string."""
        if not binary_path:
            return None
        try:
            proc = subprocess.run(
                [binary_path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            logger.debug("Failed to probe version for %s", binary_path, exc_info=True)
            return None

        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        match = _VERSION_RE.search(output)
        if match:
            return match.group(1)
        return "available" if proc.returncode == 0 else None

    def is_ffmpeg_available(self) -> bool:
        path = self.find_ffmpeg()
        return bool(path and self.get_version(path))

    def download_and_install(
        self,
        progress_callback: Callable[[int, str], None] | None = None,
        cancel_event: threading.Event | None = None,
        *,
        targets: list[tuple[str, str]] | None = None,
        client: httpx.Client | None = None,
    ) -> tuple[Path, Path | None]:
        """Download a static FFmpeg/FFprobe build into the app's user data bin directory."""
        install_targets = targets or get_ffmpeg_download_targets()
        dest_dir = get_managed_bin_dir()

        def emit(pct: int, msg: str) -> None:
            if progress_callback is not None:
                progress_callback(max(0, min(100, pct)), msg)

        emit(0, "Preparing FFmpeg download...")
        total_targets = len(install_targets)
        extracted: dict[str, Path] = {}

        own_client = client is None
        http = client or httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, connect=20.0),
            headers={"User-Agent": "LinkDownloader/2.0"},
        )
        try:
            for idx, (archive_type, url) in enumerate(install_targets):
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("FFmpeg download was cancelled.")

                base_pct = int((idx / total_targets) * 85)
                span_pct = max(1, int(85 / total_targets))
                emit(base_pct, "Downloading FFmpeg...")

                suffix = ".tar.xz" if archive_type == "tar.xz" else ".zip"
                tmp_fd, tmp_archive_str = tempfile.mkstemp(
                    prefix="ffmpeg_pkg_", suffix=suffix, dir=str(dest_dir)
                )
                os.close(tmp_fd)
                tmp_archive = Path(tmp_archive_str)

                try:
                    with http.stream("GET", url) as resp:
                        resp.raise_for_status()
                        total_bytes_hdr = resp.headers.get("content-length")
                        total_bytes = int(total_bytes_hdr) if total_bytes_hdr and total_bytes_hdr.isdigit() else 0
                        downloaded = 0
                        last_reported = -1
                        with tmp_archive.open("wb") as fp:
                            for chunk in resp.iter_bytes(chunk_size=131_072):
                                if cancel_event and cancel_event.is_set():
                                    raise InterruptedError("FFmpeg download was cancelled.")
                                if not chunk:
                                    continue
                                fp.write(chunk)
                                downloaded += len(chunk)
                                if total_bytes > 0:
                                    rel = min(1.0, downloaded / total_bytes)
                                    pct = base_pct + int(rel * span_pct)
                                    if pct > last_reported:
                                        last_reported = pct
                                        mb_done = downloaded / (1024 * 1024)
                                        mb_total = total_bytes / (1024 * 1024)
                                        emit(pct, f"Downloading FFmpeg ({mb_done:.1f} / {mb_total:.1f} MB)...")

                    emit(88, "Installing FFmpeg...")
                    if archive_type == "tar.xz":
                        extracted.update(_extract_tar_binaries(tmp_archive, dest_dir))
                    elif archive_type == "zip":
                        extracted.update(_extract_zip_binaries(tmp_archive, dest_dir))
                    else:
                        raise RuntimeError(f"Unsupported archive format: {archive_type}")
                finally:
                    with contextlib.suppress(OSError):
                        tmp_archive.unlink()
        finally:
            if own_client:
                http.close()

        emit(96, "Verifying FFmpeg...")
        ffmpeg_path = self.find_ffmpeg()
        ffprobe_path = self.find_ffprobe()
        if not ffmpeg_path or not self.get_version(ffmpeg_path):
            raise RuntimeError(
                "FFmpeg was downloaded but could not be verified on this system."
            )

        emit(100, "FFmpeg is ready")
        return Path(ffmpeg_path), Path(ffprobe_path) if ffprobe_path else None


def _install_extracted_stream(src_fp, target_name: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_str = tempfile.mkstemp(prefix=f"{target_name}.", suffix=".tmp", dir=str(dest_dir))
    os.close(tmp_fd)
    tmp_path = Path(tmp_str)
    try:
        with tmp_path.open("wb") as out_fp:
            shutil.copyfileobj(src_fp, out_fp, length=262_144)
        if sys.platform != "win32":
            tmp_path.chmod(0o755)
        final_path = dest_dir / target_name
        os.replace(tmp_path, final_path)
        return final_path
    except Exception:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise


def _extract_tar_binaries(archive_path: Path, dest_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    with tarfile.open(archive_path, mode="r:*") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            base_name = Path(member.name).name.lower()
            if base_name not in _TARGET_BINARIES:
                continue
            src = tf.extractfile(member)
            if src is None:
                continue
            with src:
                found[base_name] = _install_extracted_stream(src, base_name, dest_dir)
    return found


def _extract_zip_binaries(archive_path: Path, dest_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    with zipfile.ZipFile(archive_path, mode="r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Skip symlinks inside zip archives
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                continue
            base_name = Path(info.filename).name.lower()
            if base_name not in _TARGET_BINARIES:
                continue
            with zf.open(info, mode="r") as src:
                found[base_name] = _install_extracted_stream(src, base_name, dest_dir)
    return found
