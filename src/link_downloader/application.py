"""Application bootstrap, logging setup, Qt initialization, and smoke self-test."""

from __future__ import annotations

import contextlib
import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from link_downloader import __app_name__, __version__
from link_downloader.platform.paths import get_app_icon_path, get_log_dir
from link_downloader.services.download_manager import DownloadManager
from link_downloader.ui.main_window import MainWindow


def configure_logging(*, verbose: bool = False) -> None:
    """Configure rotating file logging and console output."""
    log_dir = get_log_dir()
    log_file = log_dir / "link-downloader.log"
    level = logging.DEBUG if verbose else logging.INFO

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    with contextlib.suppress(OSError):
        handlers.append(
            RotatingFileHandler(
                log_file,
                maxBytes=2 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def create_qt_application(argv: list[str] | None = None) -> QApplication:
    """Create or return the singleton QApplication with app metadata and icon."""
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("LinkDownloader")

    icon_path = get_app_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    return app


def run_self_test() -> int:
    """Verify Qt, SQLite history, configuration, dependency detection, and MainWindow startup."""
    configure_logging(verbose=False)
    app = create_qt_application(["link-downloader", "--self-test"])
    manager = DownloadManager()
    manager.startup()
    deps = manager.check_dependencies()
    window = MainWindow(manager)
    window.close()
    app.processEvents()
    print(
        f"SELF-TEST OK: {__app_name__} v{__version__} | "
        f"deps_checked={len(deps)} | config={manager.settings.download_folder}"
    )
    return 0


def run_gui(argv: list[str] | None = None) -> int:
    """Initialize services, migrate legacy data if present, and launch the desktop GUI."""
    configure_logging(verbose=False)
    app = create_qt_application(argv)
    manager = DownloadManager()
    manager.startup()

    window = MainWindow(manager)
    window.show()
    exit_code = app.exec()
    manager.shutdown()
    return int(exit_code)
