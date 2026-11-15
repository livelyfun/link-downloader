"""End-to-end lint, test, package build, and built-binary smoke verification script."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from link_downloader import __version__

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"


def _arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine or "unknown"


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"[verify] $ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(ROOT_DIR), check=True, env=env)


def main() -> int:
    ruff_bin = Path(sys.executable).with_name("ruff")
    ruff_cmd = [str(ruff_bin)] if ruff_bin.exists() else [sys.executable, "-m", "ruff"]

    # 1. Lint source, tests, and scripts
    _run([*ruff_cmd, "check", "src", "tests", "scripts"])

    # 2. Full automated test suite under offscreen Qt
    test_env = dict(os.environ)
    test_env.setdefault("QT_QPA_PLATFORM", "offscreen")
    _run([sys.executable, "-m", "pytest", "-v"], env=test_env)

    # 3. Build standalone bundle + platform installers
    _run([sys.executable, "scripts/build.py"])

    # 4. Smoke-verify built binary & Linux artifacts
    exe_name = "link-downloader.exe" if sys.platform == "win32" else "link-downloader"
    exe_path = DIST_DIR / "link-downloader" / exe_name
    if not exe_path.is_file():
        raise FileNotFoundError(f"Expected packaged executable missing: {exe_path}")

    with tempfile.TemporaryDirectory(prefix="ld_verify_") as tmp_dir:
        smoke_env = dict(os.environ)
        smoke_env["QT_QPA_PLATFORM"] = "offscreen"
        smoke_env["LINK_DOWNLOADER_CONFIG_DIR"] = str(Path(tmp_dir) / "cfg")
        smoke_env["LINK_DOWNLOADER_DATA_DIR"] = str(Path(tmp_dir) / "data")
        smoke_env["LINK_DOWNLOADER_CACHE_DIR"] = str(Path(tmp_dir) / "cache")
        smoke_env["LINK_DOWNLOADER_LOG_DIR"] = str(Path(tmp_dir) / "logs")

        _run([str(exe_path), "--version"], env=smoke_env)
        _run([str(exe_path), "--self-test"], env=smoke_env)

    if sys.platform.startswith("linux"):
        arch = _arch()
        darch = "amd64" if arch == "x86_64" else arch
        expected = [
            DIST_DIR / f"link-downloader-{__version__}-linux-{arch}.tar.gz",
            DIST_DIR / "AppDir" / "AppRun",
            DIST_DIR / f"link-downloader_{__version__}_{darch}.deb",
            DIST_DIR / "rpm" / "link-downloader.spec",
        ]
        for path in expected:
            if not path.exists():
                raise FileNotFoundError(f"Expected Linux artifact missing: {path}")
            print(f"[verify] Confirmed artifact: {path}")

        deb_file = DIST_DIR / f"link-downloader_{__version__}_{darch}.deb"
        with deb_file.open("rb") as fp:
            if fp.read(8) != b"!<arch>\n":
                raise RuntimeError(f"Invalid .deb archive header in {deb_file}")
        ar_bin = shutil.which("ar")
        if ar_bin:
            _run([ar_bin, "-t", str(deb_file)])

    print("\n[verify] ALL LINT, TEST, BUILD, AND PACKAGED BINARY CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
