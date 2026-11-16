"""Runtime and external dependency detection and user-friendly status reporting."""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from link_downloader.core.enums import DependencyCategory
from link_downloader.core.models import DependencyStatus, MigrationReport
from link_downloader.platform.paths import get_config_dir, get_data_dir, get_log_dir
from link_downloader.platform.system_integration import get_platform_key, get_system_summary
from link_downloader.services.ffmpeg_service import FfmpegService

_NODE_MIN = (22, 0, 0)
_DENO_MIN = (2, 3, 0)
_QUICKJS_MIN = (2023, 12, 9)


def _parse_version_tuple(raw: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", raw)
    return tuple(int(n) for n in nums[:4]) if nums else (0,)


def _import_module_version(dist_name: str) -> str | None:
    """Detect frozen or bundled packages via direct import when dist-info metadata is absent."""
    try:
        if dist_name == "PySide6":
            import PySide6

            ver = getattr(PySide6, "__version__", None)
            return str(ver) if ver else "bundled"
        if dist_name == "httpx":
            import httpx

            ver = getattr(httpx, "__version__", None)
            return str(ver) if ver else "bundled"
        if dist_name == "yt-dlp":
            import yt_dlp.version

            ver = getattr(yt_dlp.version, "__version__", None)
            return str(ver) if ver else "bundled"
        if dist_name == "yt-dlp-ejs":
            import yt_dlp_ejs

            ver = getattr(yt_dlp_ejs, "version", None)
            if not ver and hasattr(yt_dlp_ejs, "_version"):
                ver = getattr(yt_dlp_ejs._version, "__version__", None)
            if not ver:
                ver = getattr(yt_dlp_ejs, "__version__", None)
            return str(ver) if ver else "bundled"

        mod = importlib.import_module(dist_name.replace("-", "_"))
        ver = getattr(mod, "__version__", None) or getattr(mod, "version", None)
        return str(ver) if ver else "bundled"
    except Exception:
        return None


def _pkg_version(dist_name: str) -> str | None:
    try:
        ver = importlib.metadata.version(dist_name)
        if ver:
            return ver
    except Exception:
        pass
    return _import_module_version(dist_name)


def _pkg_location() -> str:
    if getattr(sys, "frozen", False):
        return "Bundled inside Prism Link Downloader"
    return "Built-in application component"


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
        """Inspect all built-in and external components with non-technical guidance."""
        # Core bundled Python components
        pyside_ver = _pkg_version("PySide6")
        httpx_ver = _pkg_version("httpx")
        ytdlp_ver = _pkg_version("yt-dlp")
        ejs_ver = _pkg_version("yt-dlp-ejs")
        pkg_loc = _pkg_location()

        ffmpeg_path = self._ffmpeg.find_ffmpeg()
        ffmpeg_ver = self._ffmpeg.get_version(ffmpeg_path)
        ffprobe_path = self._ffmpeg.find_ffprobe()
        ffprobe_ver = self._ffmpeg.get_version(ffprobe_path)

        js_info = self._find_js_runtime()
        js_available = bool(js_info and js_info[3])
        js_version = f"{js_info[0]} {js_info[2]}" if js_info else None
        js_path = js_info[1] if js_info else None

        return [
            DependencyStatus(
                name="PySide6 (Qt 6)",
                category=DependencyCategory.REQUIRED,
                available=pyside_ver is not None,
                version=pyside_ver,
                path=pkg_loc if pyside_ver is not None else None,
                impact="Provides the native desktop window and interface.",
                install_hint="Included with Prism Link Downloader.",
                verify_command="Checked automatically",
            ),
            DependencyStatus(
                name="HTTPX",
                category=DependencyCategory.REQUIRED,
                available=httpx_ver is not None,
                version=httpx_ver,
                path=pkg_loc if httpx_ver is not None else None,
                impact="Downloads direct files and links reliably.",
                install_hint="Included with Prism Link Downloader.",
                verify_command="Checked automatically",
            ),
            DependencyStatus(
                name="yt-dlp Python API",
                category=DependencyCategory.REQUIRED,
                available=ytdlp_ver is not None,
                version=ytdlp_ver,
                path=pkg_loc if ytdlp_ver is not None else None,
                impact="Finds video and audio formats from supported websites.",
                install_hint="Included with Prism Link Downloader.",
                verify_command="Checked automatically",
            ),
            DependencyStatus(
                name="yt-dlp-ejs",
                category=DependencyCategory.RECOMMENDED,
                available=ejs_ver is not None,
                version=ejs_ver,
                path=pkg_loc if ejs_ver is not None else None,
                impact="Built-in helper for modern YouTube video extraction.",
                install_hint="Included with Prism Link Downloader.",
                verify_command="Checked automatically",
            ),
            DependencyStatus(
                name="FFmpeg",
                category=DependencyCategory.RECOMMENDED,
                available=bool(ffmpeg_path and ffmpeg_ver),
                version=ffmpeg_ver,
                path=ffmpeg_path,
                impact="Recommended for merging high-quality video and converting audio.",
                install_hint="Click 'Download FFmpeg' to install automatically inside the app.",
                verify_command="Checked automatically",
            ),
            DependencyStatus(
                name="FFprobe",
                category=DependencyCategory.OPTIONAL,
                available=bool(ffprobe_path and ffprobe_ver),
                version=ffprobe_ver,
                path=ffprobe_path,
                impact="Helps inspect media stream duration, resolution, and audio details.",
                install_hint="Installed automatically when you click 'Download FFmpeg'.",
                verify_command="Checked automatically",
            ),
            DependencyStatus(
                name="JavaScript Runtime (Deno / Node.js)",
                category=DependencyCategory.OPTIONAL,
                available=js_available,
                version=js_version,
                path=js_path,
                impact="Optional system runtime for complex web player challenges.",
                install_hint="Optional — Prism Link Downloader already includes built-in YouTube support (yt-dlp-ejs).",
                verify_command="Checked automatically",
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
    def format_diagnostic_report(
        statuses: list[DependencyStatus],
        migration_report: MigrationReport | None = None,
    ) -> str:
        """Build a clear, user-friendly plain-text status summary."""
        summary = get_system_summary()
        lines = [
            f"Application: {summary.app_name} v{summary.app_version}",
            f"Mode: {'Packaged Desktop App' if summary.is_frozen else 'Development Build'}",
            f"System: {summary.os_name} {summary.os_release} ({summary.architecture})",
            f"Settings Folder: {get_config_dir()}",
            f"Data Folder: {get_data_dir()}",
            f"Log Folder: {get_log_dir()}",
        ]
        if migration_report is not None:
            lines.append(
                f"Previous Data Imported: {migration_report.history_imported_count} items"
                if migration_report.history_imported_count
                else "Previous Data Imported: None"
            )
        lines.extend(["", "Components:"])
        for dep in statuses:
            badge = "Available" if dep.available else (
                "Not Installed" if dep.category == DependencyCategory.RECOMMENDED else "Optional (Not Installed)"
            )
            ver = f"v{dep.version}" if dep.version else "Not detected"
            lines.append(f"• {dep.name}: {badge} ({ver})")
            if dep.path:
                lines.append(f"  Location: {dep.path}")
            if not dep.available:
                lines.append(f"  Note: {dep.impact}")
                lines.append(f"  How to add: {dep.install_hint}")
        return "\n".join(lines)

    @staticmethod
    def environment_diagnostics() -> dict[str, str]:
        """Return safe non-secret environment diagnostics for troubleshooting."""
        return {
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
            "path_env": os.environ.get("PATH", ""),
        }
