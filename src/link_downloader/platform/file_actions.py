"""Cross-platform OS actions for opening files and revealing items in the file manager."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _open_via_qt(target: Path) -> bool:
    """Attempt to open a local file or directory using Qt's QDesktopServices."""
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is not None:
            return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))))
    except Exception:
        logger.debug("QDesktopServices fallback unavailable", exc_info=True)
    return False


def _open_native(target: Path) -> bool:
    """Open a local path with the OS default handler without shell interpolation."""
    if _open_via_qt(target):
        return True

    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
            return True
        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, str(target)])
            return True
    except Exception:
        logger.warning("Failed to open path %s", target, exc_info=True)
    return False


def open_file(file_path: str | Path) -> bool:
    """Open a downloaded file with its associated system application."""
    target = Path(file_path).expanduser().resolve()
    if not target.exists():
        return False
    return _open_native(target)


def open_folder(folder_path: str | Path) -> bool:
    """Open a folder in the OS file manager, creating it first if necessary."""
    target = Path(folder_path).expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True)
        resolved = target.resolve()
    except OSError:
        logger.warning("Unable to prepare folder %s", folder_path, exc_info=True)
        return False
    return _open_native(resolved)


def reveal_in_file_manager(file_path: str | Path | None, fallback_folder: str | Path | None = None) -> bool:
    """Highlight a file in the OS file manager, or open its parent/fallback folder."""
    if file_path:
        target = Path(file_path).expanduser()
        if target.exists():
            resolved = target.resolve()
            try:
                if sys.platform == "win32":
                    subprocess.Popen(["explorer", f"/select,{resolved}"])
                    return True
                if sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", str(resolved)])
                    return True

                dbus_send = shutil.which("dbus-send")
                if dbus_send:
                    file_uri = resolved.as_uri()
                    result = subprocess.run(
                        [
                            dbus_send,
                            "--session",
                            "--dest=org.freedesktop.FileManager1",
                            "--type=method_call",
                            "--print-reply",
                            "/org/freedesktop/FileManager1",
                            "org.freedesktop.FileManager1.ShowItems",
                            f"array:string:{file_uri}",
                            "string:",
                        ],
                        capture_output=True,
                        timeout=2,
                        check=False,
                    )
                    if result.returncode == 0:
                        return True
            except Exception:
                logger.debug("File manager highlight failed; falling back to parent folder", exc_info=True)

            if resolved.parent.exists():
                return _open_native(resolved.parent)

        if target.parent.exists():
            return _open_native(target.parent)

    if fallback_folder:
        return open_folder(fallback_folder)
    return False
