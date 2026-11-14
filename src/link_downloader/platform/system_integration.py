"""OS metadata, diagnostics, and Qt desktop integration helpers."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass

from link_downloader import __app_name__, __version__


@dataclass(frozen=True, slots=True)
class SystemSummary:
    """Diagnostic summary of the host platform and Python runtime."""

    app_name: str
    app_version: str
    os_name: str
    os_release: str
    architecture: str
    python_version: str
    is_frozen: bool


def get_system_summary() -> SystemSummary:
    """Collect non-sensitive platform and runtime details for diagnostics."""
    return SystemSummary(
        app_name=__app_name__,
        app_version=__version__,
        os_name=platform.system(),
        os_release=platform.release(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        is_frozen=bool(getattr(sys, "frozen", False)),
    )


def get_platform_key() -> str:
    """Return a normalized platform key: linux, windows, or macos."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"
