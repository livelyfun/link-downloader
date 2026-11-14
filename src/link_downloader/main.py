"""CLI and GUI entry point for Link Downloader."""

from __future__ import annotations

import argparse
import sys

from link_downloader import __app_name__, __version__
from link_downloader.application import run_gui, run_self_test


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="link-downloader",
        description=f"{__app_name__} — cross-platform desktop media and file downloader.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print application version and exit.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Initialize Qt, SQLite, settings, and dependency checks, then exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, remaining = parser.parse_known_args(argv)
    if args.version:
        print(f"{__app_name__} {__version__}")
        return 0
    if args.self_test:
        return run_self_test()
    return run_gui([sys.argv[0], *remaining])


if __name__ == "__main__":
    raise SystemExit(main())
