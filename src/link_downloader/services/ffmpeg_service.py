"""FFmpeg and FFprobe discovery and version probing."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

from link_downloader.platform.paths import get_assets_dir

logger = logging.getLogger(__name__)
_VERSION_RE = re.compile(r"(?:ffmpeg|ffprobe)\s+version\s+(\S+)", re.IGNORECASE)


class FfmpegService:
    """Locates FFmpeg/FFprobe binaries and verifies availability without shell execution."""

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
