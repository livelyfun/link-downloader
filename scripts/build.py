"""Cross-platform build and packaging script for Link Downloader."""

from __future__ import annotations

import argparse
import io
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
ASSETS_DIR = ROOT_DIR / "assets"
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from link_downloader import __app_name__, __version__  # noqa: E402

DESKTOP_ENTRY_TEMPLATE = """[Desktop Entry]
Type=Application
Name=Link Downloader
Comment=Download videos, audio, and files from supported URLs and direct links
Exec=/usr/bin/link-downloader %U
Icon=link-downloader
Terminal=false
Categories=Network;AudioVideo;Utility;
StartupWMClass=Link Downloader
"""


def _host_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine or "unknown"


def _deb_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine or "amd64"


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print(f"[build] Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd or ROOT_DIR), check=True)


def _build_with_pyinstaller() -> Path:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "link-downloader",
        "--paths",
        str(SRC_DIR),
        "--add-data",
        f"{ASSETS_DIR}{os.pathsep}assets",
        "--collect-data",
        "yt_dlp_ejs",
        "--hidden-import",
        "yt_dlp_ejs",
    ]
    if sys.platform == "win32":
        ico = ASSETS_DIR / "icons" / "app_icon.ico"
        if ico.exists():
            cmd.extend(["--icon", str(ico)])
    elif sys.platform == "linux":
        png = ASSETS_DIR / "icons" / "app_icon.png"
        if png.exists():
            cmd.extend(["--icon", str(png)])

    cmd.append(str(SRC_DIR / "link_downloader" / "main.py"))
    _run(cmd)
    return DIST_DIR / "link-downloader"


def _build_with_pyside6_deploy() -> Path:
    tool = shutil.which("pyside6-deploy") or str(Path(sys.executable).with_name("pyside6-deploy"))
    if not Path(tool).exists() and shutil.which("pyside6-deploy") is None:
        raise RuntimeError("pyside6-deploy was not found in the active environment.")
    cmd = [
        tool,
        str(SRC_DIR / "link_downloader" / "main.py"),
        "--name",
        "link-downloader",
        "--force",
    ]
    _run(cmd)
    return DIST_DIR / "link-downloader"


def _build_with_nuitka() -> Path:
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        "--output-dir=dist",
        "--output-filename=link-downloader",
        f"--include-data-dir={ASSETS_DIR}=assets",
        str(SRC_DIR / "link_downloader" / "main.py"),
    ]
    _run(cmd)
    return DIST_DIR / "link-downloader"


def _write_ar_member(fp, name: str, payload: bytes, mtime: int) -> None:
    if len(name) > 16:
        raise ValueError(f"ar member name too long: {name}")
    header = (
        f"{name:<16}"
        f"{mtime:<12}"
        f"{0:<6}"
        f"{0:<6}"
        f"{'100644':<8}"
        f"{len(payload):<10}"
        "`\n"
    ).encode("ascii")
    assert len(header) == 60
    fp.write(header)
    fp.write(payload)
    if len(payload) % 2 == 1:
        fp.write(b"\n")


def _tar_gz_directory(root_dir: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tf:
        for path in sorted(root_dir.rglob("*")):
            rel = path.relative_to(root_dir).as_posix()
            arcname = f"./{rel}"
            info = tf.gettarinfo(str(path), arcname=arcname)
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            if path.is_symlink():
                tf.addfile(info)
            elif path.is_dir():
                info.mode = 0o755
                tf.addfile(info)
            else:
                mode = stat.S_IMODE(path.stat().st_mode)
                info.mode = 0o755 if (mode & 0o111) else 0o644
                with path.open("rb") as src_fp:
                    tf.addfile(info, src_fp)
    return buf.getvalue()


def _create_pure_python_deb(staging_dir: Path, out_deb: Path) -> None:
    control_dir = staging_dir / "DEBIAN"
    data_root = staging_dir

    control_buf = io.BytesIO()
    with tarfile.open(fileobj=control_buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tf:
        for item in sorted(control_dir.rglob("*")):
            rel = item.relative_to(control_dir).as_posix()
            info = tf.gettarinfo(str(item), arcname=f"./{rel}")
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mode = 0o644 if item.is_file() else 0o755
            if item.is_file():
                with item.open("rb") as fp:
                    tf.addfile(info, fp)
            else:
                tf.addfile(info)

    # Create temporary copy without DEBIAN directory for data.tar.gz
    data_buf = io.BytesIO()
    with tarfile.open(fileobj=data_buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tf:
        for item in sorted(data_root.rglob("*")):
            rel_parts = item.relative_to(data_root).parts
            if rel_parts and rel_parts[0] == "DEBIAN":
                continue
            arcname = f"./{item.relative_to(data_root).as_posix()}"
            info = tf.gettarinfo(str(item), arcname=arcname)
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            if item.is_symlink():
                tf.addfile(info)
            elif item.is_dir():
                info.mode = 0o755
                tf.addfile(info)
            else:
                mode = stat.S_IMODE(item.stat().st_mode)
                info.mode = 0o755 if (mode & 0o111) else 0o644
                with item.open("rb") as fp:
                    tf.addfile(info, fp)

    now = int(time.time())
    with out_deb.open("wb") as fp:
        fp.write(b"!<arch>\n")
        _write_ar_member(fp, "debian-binary", b"2.0\n", now)
        _write_ar_member(fp, "control.tar.gz", control_buf.getvalue(), now)
        _write_ar_member(fp, "data.tar.gz", data_buf.getvalue(), now)


def _package_linux(bundle_dir: Path) -> dict[str, Path]:
    artifacts: dict[str, Path] = {"bundle": bundle_dir}
    arch = _host_arch()
    darch = _deb_arch()

    # 1. Portable tar.gz
    tar_path = DIST_DIR / f"link-downloader-{__version__}-linux-{arch}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(bundle_dir, arcname=f"link-downloader-{__version__}-linux-{arch}")
    artifacts["tar_gz"] = tar_path

    # 2. AppDir + optional AppImage
    appdir = DIST_DIR / "AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    opt_dir = appdir / "opt" / "link-downloader"
    shutil.copytree(bundle_dir, opt_dir, symlinks=True)

    icon_src = ASSETS_DIR / "icons" / "app_icon.png"
    icon_dest = appdir / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps" / "link-downloader.png"
    icon_dest.parent.mkdir(parents=True, exist_ok=True)
    if icon_src.exists():
        shutil.copy2(icon_src, icon_dest)
        shutil.copy2(icon_src, appdir / "link-downloader.png")
        shutil.copy2(icon_src, appdir / ".DirIcon")

    desktop_appdir = appdir / "link-downloader.desktop"
    desktop_appdir.write_text(
        DESKTOP_ENTRY_TEMPLATE.replace("Exec=/usr/bin/link-downloader %U", "Exec=link-downloader %U"),
        encoding="utf-8",
    )
    usr_apps = appdir / "usr" / "share" / "applications"
    usr_apps.mkdir(parents=True, exist_ok=True)
    shutil.copy2(desktop_appdir, usr_apps / "link-downloader.desktop")

    apprun = appdir / "AppRun"
    apprun.write_text(
        '#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
        'exec "$HERE/opt/link-downloader/link-downloader" "$@"\n',
        encoding="utf-8",
    )
    apprun.chmod(0o755)
    artifacts["appdir"] = appdir

    appimagetool = shutil.which("appimagetool")
    if appimagetool:
        appimage_out = DIST_DIR / f"Link_Downloader-{__version__}-{arch}.AppImage"
        env = dict(os.environ, ARCH=arch)
        subprocess.run([appimagetool, str(appdir), str(appimage_out)], check=True, env=env)
        artifacts["appimage"] = appimage_out

    # 3. Debian .deb package
    deb_stage = BUILD_DIR / "deb_staging"
    if deb_stage.exists():
        shutil.rmtree(deb_stage)
    deb_opt = deb_stage / "opt" / "link-downloader"
    shutil.copytree(bundle_dir, deb_opt, symlinks=True)

    usr_bin = deb_stage / "usr" / "bin"
    usr_bin.mkdir(parents=True, exist_ok=True)
    launcher = usr_bin / "link-downloader"
    launcher.write_text("#!/bin/sh\nexec /opt/link-downloader/link-downloader \"$@\"\n", encoding="utf-8")
    launcher.chmod(0o755)

    deb_apps = deb_stage / "usr" / "share" / "applications"
    deb_apps.mkdir(parents=True, exist_ok=True)
    (deb_apps / "link-downloader.desktop").write_text(DESKTOP_ENTRY_TEMPLATE, encoding="utf-8")

    if icon_src.exists():
        deb_icon = (
            deb_stage / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps" / "link-downloader.png"
        )
        deb_icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon_src, deb_icon)

    debian_dir = deb_stage / "DEBIAN"
    debian_dir.mkdir(parents=True, exist_ok=True)
    installed_kb = sum(p.stat().st_size for p in deb_opt.rglob("*") if p.is_file()) // 1024
    (debian_dir / "control").write_text(
        f"Package: link-downloader\n"
        f"Version: {__version__}\n"
        f"Section: net\n"
        f"Priority: optional\n"
        f"Architecture: {darch}\n"
        f"Installed-Size: {installed_kb}\n"
        f"Maintainer: Mithlesh Kumar Das <196286275+livelyfun@users.noreply.github.com>\n"
        f"Depends: libc6, libgl1, libegl1, libxkbcommon0, libxcb-cursor0\n"
        f"Recommends: ffmpeg, nodejs\n"
        f"Description: {__app_name__} cross-platform desktop downloader\n"
        f" Native PySide6 desktop application supporting media URLs via yt-dlp\n"
        f" and direct HTTP/HTTPS file downloads.\n",
        encoding="utf-8",
    )

    deb_out = DIST_DIR / f"link-downloader_{__version__}_{darch}.deb"
    dpkg_deb = shutil.which("dpkg-deb")
    if dpkg_deb:
        _run([dpkg_deb, "--build", "--root-owner-group", str(deb_stage), str(deb_out)])
    else:
        _create_pure_python_deb(deb_stage, deb_out)
    artifacts["deb"] = deb_out

    # 4. RPM spec (+ optional rpmbuild)
    rpm_dir = DIST_DIR / "rpm"
    rpm_dir.mkdir(parents=True, exist_ok=True)
    spec_path = rpm_dir / "link-downloader.spec"
    spec_path.write_text(
        f"Name:           link-downloader\n"
        f"Version:        {__version__}\n"
        f"Release:        1%{{?dist}}\n"
        f"Summary:        {__app_name__} cross-platform desktop downloader\n"
        f"License:        MIT\n"
        f"Recommends:     ffmpeg\n\n"
        f"%description\n"
        f"Native PySide6 desktop downloader supporting yt-dlp extraction and HTTP/HTTPS streaming.\n\n"
        f"%install\n"
        f"mkdir -p %{{buildroot}}/opt/link-downloader %{{buildroot}}/usr/bin "
        f"%{{buildroot}}/usr/share/applications %{{buildroot}}/usr/share/icons/hicolor/512x512/apps\n"
        f"cp -a {bundle_dir}/* %{{buildroot}}/opt/link-downloader/\n"
        f"install -m 0755 {launcher} %{{buildroot}}/usr/bin/link-downloader\n"
        f"install -m 0644 {deb_apps / 'link-downloader.desktop'} %{{buildroot}}/usr/share/applications/link-downloader.desktop\n"
        f"install -m 0644 {icon_src} %{{buildroot}}/usr/share/icons/hicolor/512x512/apps/link-downloader.png\n\n"
        f"%files\n"
        f"/opt/link-downloader\n"
        f"/usr/bin/link-downloader\n"
        f"/usr/share/applications/link-downloader.desktop\n"
        f"/usr/share/icons/hicolor/512x512/apps/link-downloader.png\n",
        encoding="utf-8",
    )
    artifacts["rpm_spec"] = spec_path

    rpmbuild = shutil.which("rpmbuild")
    if rpmbuild:
        try:
            _run(
                [
                    rpmbuild,
                    "-bb",
                    "--define",
                    f"_topdir {BUILD_DIR / 'rpmbuild'}",
                    "--define",
                    f"_rpmdir {rpm_dir}",
                    str(spec_path),
                ]
            )
            rpms = list(rpm_dir.rglob("*.rpm"))
            if rpms:
                artifacts["rpm"] = rpms[0]
        except subprocess.CalledProcessError as exc:
            print(f"[build] Warning: rpmbuild failed cleanly ({exc}); keeping spec file.")

    return artifacts


def _package_windows(bundle_dir: Path) -> dict[str, Path]:
    arch = _host_arch()
    zip_path = DIST_DIR / f"link-downloader-{__version__}-windows-{arch}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(bundle_dir.rglob("*")):
            if file_path.is_file():
                arc = Path(f"link-downloader-{__version__}-windows-{arch}") / file_path.relative_to(
                    bundle_dir
                )
                zf.write(file_path, arcname=arc.as_posix())
    return {"bundle": bundle_dir, "zip": zip_path}


def _package_macos(bundle_dir: Path) -> dict[str, Path]:
    artifacts: dict[str, Path] = {"bundle": bundle_dir}
    arch = _host_arch()
    app_bundle = DIST_DIR / "Link Downloader.app"
    if app_bundle.exists():
        shutil.rmtree(app_bundle)

    pyinstaller_app = DIST_DIR / "link-downloader.app"
    if pyinstaller_app.exists():
        shutil.copytree(pyinstaller_app, app_bundle, symlinks=True)
    else:
        contents = app_bundle / "Contents"
        macos_dir = contents / "MacOS"
        res_dir = contents / "Resources"
        macos_dir.mkdir(parents=True, exist_ok=True)
        res_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundle_dir, macos_dir / "bundle", symlinks=True)
        launcher = macos_dir / "link-downloader"
        launcher.write_text('#!/bin/sh\nexec "$(dirname "$0")/bundle/link-downloader" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
        (contents / "Info.plist").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            f'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            f'<plist version="1.0"><dict>\n'
            f'  <key>CFBundleName</key><string>Link Downloader</string>\n'
            f'  <key>CFBundleExecutable</key><string>link-downloader</string>\n'
            f'  <key>CFBundleIdentifier</key><string>io.github.livelyfun.LinkDownloader</string>\n'
            f'  <key>CFBundleVersion</key><string>{__version__}</string>\n'
            f'</dict></plist>\n',
            encoding="utf-8",
        )
    artifacts["app"] = app_bundle

    hdiutil = shutil.which("hdiutil")
    if hdiutil:
        dmg_path = DIST_DIR / f"LinkDownloader-{__version__}-macos-{arch}.dmg"
        _run(
            [
                hdiutil,
                "create",
                "-volname",
                "Link Downloader",
                "-srcfolder",
                str(app_bundle),
                "-ov",
                "-format",
                "UDZO",
                str(dmg_path),
            ]
        )
        artifacts["dmg"] = dmg_path
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build standalone Link Downloader packages.")
    parser.add_argument(
        "--packager",
        choices=["pyinstaller", "pyside6-deploy", "nuitka"],
        default="pyinstaller",
        help="Packaging backend to use.",
    )
    args = parser.parse_args(argv)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    if args.packager == "pyinstaller":
        bundle_dir = _build_with_pyinstaller()
    elif args.packager == "pyside6-deploy":
        bundle_dir = _build_with_pyside6_deploy()
    else:
        bundle_dir = _build_with_nuitka()

    if sys.platform.startswith("linux"):
        artifacts = _package_linux(bundle_dir)
    elif sys.platform == "win32":
        artifacts = _package_windows(bundle_dir)
    elif sys.platform == "darwin":
        artifacts = _package_macos(bundle_dir)
    else:
        artifacts = {"bundle": bundle_dir}

    print("\n[build] Built artifacts:")
    for key, path in artifacts.items():
        size = path.stat().st_size if path.is_file() else sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        print(f"  - {key}: {path} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
