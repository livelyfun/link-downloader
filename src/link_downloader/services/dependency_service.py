"""Runtime and external dependency detection and diagnostic guidance."""

from __future__ import annotations

import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from link_downloader.core.enums import DependencyCategory
from link_downloader.core.models import DependencyStatus
from link_downloader.platform.system_integration import get_platform_key
from link_downloader.services.ffmpeg_service import FfmpegService

_NODE_MIN = (22, 0, 0)
_DENO_MIN = (2, 3, 0)
_QUICKJS_MIN = (2023, 12, 9)


def _parse_version_tuple(raw: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", raw)
    return tuple(int(n) for n in nums[:4]) if nums else (0,)


def _pkg_version(dist_name: str) -> str | None:
    try:
        return importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _run_version(cmd: list[str], pattern: str) -> str | None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        match = re.search(pattern, output, re.MULTILINE)
        if match:
            return match.group(1).strip()
        if proc.returncode == 0 and output.strip():
            return output.strip().splitlines()[0]
    except Exception:
        return None
    return None


class DependencyService:
    """Detects required, recommended, and optional libraries/tools across platforms."""

    def __init__(self, ffmpeg_service: FfmpegService | None = None) -> None:
        self._ffmpeg = ffmpeg_service or FfmpegService()

    def _find_js_runtime(self) -> tuple[str, str, str, bool] | None:
        """Return (name, path, version, meets_min_version) for the best available JS runtime."""
        home = Path.home()
        platform_key = get_platform_key()

        # 1. Deno (preferred by yt-dlp by default)
        deno_candidates: list[Path] = []
        which_deno = shutil.which("deno")
        if which_deno:
            deno_candidates.append(Path(which_deno))
        deno_exe = "deno.exe" if platform_key == "windows" else "deno"
        deno_candidates.extend(
            [
                home / ".deno" / "bin" / deno_exe,
                home / ".local" / "bin" / deno_exe,
                Path("/opt/homebrew/bin") / deno_exe,
                Path("/usr/local/bin") / deno_exe,
            ]
        )
        for candidate in deno_candidates:
            if candidate.is_file():
                ver = _run_version([str(candidate), "--version"], r"^deno\s+(\S+)")
                if ver:
                    meets = _parse_version_tuple(ver) >= _DENO_MIN
                    return ("deno", str(candidate.resolve()), ver, meets)

        # 2. Node.js (supported when explicitly passed in js_runtimes)
        node_candidates: list[Path] = []
        which_node = shutil.which("node")
        if which_node:
            node_candidates.append(Path(which_node))
        node_exe = "node.exe" if platform_key == "windows" else "node"
        for pattern_dir in sorted(home.glob(".local/node*"), reverse=True):
            node_candidates.append(pattern_dir / "bin" / node_exe)
        node_candidates.extend(
            [
                home / ".local" / "bin" / node_exe,
                Path("/opt/homebrew/bin") / node_exe,
                Path("/usr/local/bin") / node_exe,
                Path("/usr/bin") / node_exe,
            ]
        )
        for candidate in node_candidates:
            if candidate.is_file():
                ver = _run_version([str(candidate), "--version"], r"^v?(\d+\.\d+\.\d+)")
                if ver:
                    meets = _parse_version_tuple(ver) >= _NODE_MIN
                    return ("node", str(candidate.resolve()), ver, meets)

        # 3. QuickJS / QuickJS-ng
        qjs = shutil.which("qjs")
        if qjs:
            ver = _run_version([qjs, "--help"], r"QuickJS(?:-ng)?\s+version\s+(\S+)") or "available"
            meets = _parse_version_tuple(ver) >= _QUICKJS_MIN or "ng" in ver.lower()
            return ("quickjs", str(Path(qjs).resolve()), ver, meets)

        return None

    def get_ytdlp_js_runtimes(self) -> dict[str, dict[str, str]]:
        """Build the `js_runtimes` dictionary expected by yt_dlp.YoutubeDL."""
        found = self._find_js_runtime()
        if found is None:
            return {}
        name, path, _ver, _meets = found
        return {name: {"path": path}}

    def check_all(self) -> list[DependencyStatus]:
        """Inspect all required, recommended, and optional dependencies."""
        platform_key = get_platform_key()

        # Python core packages
        pyside_ver = _pkg_version("PySide6")
        httpx_ver = _pkg_version("httpx")
        ytdlp_ver = _pkg_version("yt-dlp")
        ejs_ver = _pkg_version("yt-dlp-ejs")

        if not ytdlp_ver:
            try:
                import yt_dlp.version

                ytdlp_ver = yt_dlp.version.__version__
            except Exception:
                ytdlp_ver = None

        ffmpeg_path = self._ffmpeg.find_ffmpeg()
        ffmpeg_ver = self._ffmpeg.get_version(ffmpeg_path)
        ffprobe_path = self._ffmpeg.find_ffprobe()
        ffprobe_ver = self._ffmpeg.get_version(ffprobe_path)

        js_info = self._find_js_runtime()
        js_available = bool(js_info and js_info[3])
        js_version = f"{js_info[0]} {js_info[2]}" if js_info else None
        js_path = js_info[1] if js_info else None

        ffmpeg_hint = {
            "windows": "winget install Gyan.FFmpeg  (or choco install ffmpeg)",
            "macos": "brew install ffmpeg",
            "linux": "Debian/Ubuntu: sudo apt install ffmpeg  |  Fedora: sudo dnf install ffmpeg",
        }[platform_key]

        js_hint = {
            "windows": "winget install DenoLand.Deno  (recommended Deno 2.3+ or Node.js 22+)",
            "macos": "brew install deno  (or brew install node)",
            "linux": "Install Deno 2.3+ (https://deno.com) or Node.js 22+ via your package manager",
        }[platform_key]

        return [
            DependencyStatus(
                name="PySide6 (Qt 6)",
                category=DependencyCategory.REQUIRED,
                available=pyside_ver is not None,
                version=pyside_ver,
                path=sys.executable,
                impact="Provides the native cross-platform desktop interface.",
                install_hint="pip install PySide6",
                verify_command="python -c 'import PySide6; print(PySide6.__version__)'",
            ),
            DependencyStatus(
                name="HTTPX",
                category=DependencyCategory.REQUIRED,
                available=httpx_ver is not None,
                version=httpx_ver,
                path=sys.executable,
                impact="Powers direct HTTP/HTTPS streaming file downloads and header probing.",
                install_hint="pip install httpx",
                verify_command="python -c 'import httpx; print(httpx.__version__)'",
            ),
            DependencyStatus(
                name="yt-dlp Python API",
                category=DependencyCategory.REQUIRED,
                available=ytdlp_ver is not None,
                version=ytdlp_ver,
                path=sys.executable,
                impact="Extracts metadata and media streams from supported video/audio websites.",
                install_hint='pip install -U "yt-dlp[default]"',
                verify_command="python -c 'import yt_dlp; print(yt_dlp.version.__version__)'",
            ),
            DependencyStatus(
                name="yt-dlp-ejs",
                category=DependencyCategory.RECOMMENDED,
                available=ejs_ver is not None,
                version=ejs_ver,
                path=sys.executable,
                impact="Provides external JS challenge-solving components required for full YouTube format extraction.",
                install_hint='pip install -U "yt-dlp[default]"  (or pip install -U yt-dlp-ejs)',
                verify_command="python -c 'import yt_dlp_ejs'",
            ),
            DependencyStatus(
                name="JavaScript Runtime (Deno / Node.js)",
                category=DependencyCategory.RECOMMENDED,
                available=js_available,
                version=js_version,
                path=js_path,
                impact="Executed by yt-dlp-ejs to solve YouTube player signatures; without it some formats may be unavailable.",
                install_hint=js_hint,
                verify_command="deno --version  (or node --version)",
            ),
            DependencyStatus(
                name="FFmpeg",
                category=DependencyCategory.RECOMMENDED,
                available=bool(ffmpeg_path and ffmpeg_ver),
                version=ffmpeg_ver,
                path=ffmpeg_path,
                impact="Required for merging high-resolution video+audio streams (1080p+) and converting audio to MP3.",
                install_hint=ffmpeg_hint,
                verify_command="ffmpeg -version",
            ),
            DependencyStatus(
                name="FFprobe",
                category=DependencyCategory.OPTIONAL,
                available=bool(ffprobe_path and ffprobe_ver),
                version=ffprobe_ver,
                path=ffprobe_path,
                impact="Assists yt-dlp post-processors with stream inspection and metadata embedding.",
                install_hint=ffmpeg_hint,
                verify_command="ffprobe -version",
            ),
        ]

    @staticmethod
    def missing_recommended_summary(statuses: list[DependencyStatus]) -> list[DependencyStatus]:
        """Return required or recommended dependencies that are currently unavailable."""
        return [
            s
            for s in statuses
            if not s.available
            and s.category in (DependencyCategory.REQUIRED, DependencyCategory.RECOMMENDED)
        ]

    @staticmethod
    def environment_diagnostics() -> dict[str, str]:
        """Return safe non-secret environment diagnostics for troubleshooting."""
        return {
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
            "path_env": os.environ.get("PATH", ""),
        }
