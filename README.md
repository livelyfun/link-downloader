# Link Downloader

[![GitHub Release](https://img.shields.io/github/v/release/livelyfun/link-downloader?style=flat-square&logo=github)](https://github.com/livelyfun/link-downloader/releases/latest)

**Cross-platform native Python desktop downloader built with PySide6 (Qt 6 Widgets), `yt-dlp`, `httpx`, and SQLite.**

Link Downloader replaces the previous Debian-only Electron/React application ("YT Downloader") with a zero-Electron, pure-Python desktop application for **Windows 10/11**, **macOS (Apple Silicon & Intel)**, and **Linux (Ubuntu, Debian, Linux Mint, Fedora, Arch, and derivatives)**.

---

## 1. Overview

Link Downloader inspects submitted URLs through a centralized capability resolver before starting any transfer:

- **Supported video & audio platforms** (YouTube, Vimeo, Dailymotion, SoundCloud, and the full maintained `yt-dlp` extractor catalog) are probed via the `yt-dlp` Python API (`yt_dlp.YoutubeDL`), presenting only formats genuinely reported by the source.
- **Direct HTTP/HTTPS files** (`.mp4`, `.webm`, `.mp3`, `.pdf`, `.zip`, images, archives, installers, and extensionless downloads with reliable `Content-Type` / `Content-Disposition` metadata) are streamed directly to `.part` files using `httpx` without loading large payloads into memory.
- **Generic webpages** are checked for extractable media via `yt-dlp`; plain HTML webpages are rejected safely rather than saved as fake video files.

All persistent history is stored locally in SQLite and preferences in JSON—no local web server, cloud service, account login, or browser runtime is required.

---

## 2. Features

- **Native PySide6 Qt 6 Desktop Interface**: Sidebar navigation across **Download**, **Download Queue**, **History**, and **Settings**, with a modern Dark theme (default, indigo/violet accents) and Light theme toggle.
- **Automatic Link Detection & Metadata Preview**: Paste, type, or drag-and-drop URLs; displays title, thumbnail preview, source platform/host, uploader, duration, view count, or direct file headers (`Content-Type`, size, `Accept-Ranges` resume support).
- **Accurate Format & Codec Filtering**: Filter between *All*, *Video + Audio*, *Video Only*, and *Audio Only*; see codec pairs, container, exact/approximate file size, and explicit FFmpeg merge/conversion notices (`Convert to MP3` preset included).
- **Multi-Download Queue**: Configurable concurrency (1–5 parallel jobs), real-time speed/ETA/percentage bars, cooperative pause/resume (when supported by the engine/server), cancel with `.part` cleanup, and Retry Failed.
- **SQLite Download History**: Search by title, filename, URL, or host; filter by status or source; open files, reveal in file manager, or re-download.
- **Automatic Legacy Migration**: One-time idempotent import of `~/.config/yt-downloader/config.json` and `history.json` into the new platform-standard configuration and SQLite database, preserving backups.
- **Integrated Dependency Diagnostics**: Built-in status banner and Diagnostics Dialog checking Python libraries, FFmpeg, FFprobe, `yt-dlp-ejs`, and JavaScript runtimes (`deno`, `node`, `quickjs`).

---

## 3. Supported Link Types

1. **Media Platforms (`YtDlpEngine`)**: Any site supported by the installed `yt-dlp` extractor catalog (including YouTube, YouTube Shorts, Vimeo, Dailymotion, SoundCloud, etc.), plus playlist inspection (`playlist_count` surfaced).
2. **Direct File URLs (`DirectHttpEngine`)**: Streaming HTTP/HTTPS downloads for video/audio containers, images, PDFs, archives, documents, executables/packages (`.deb`, `.rpm`, `.dmg`, `.exe`), and extensionless endpoints returning file headers.
3. **Generic Media Webpages (`UrlCapabilityResolver`)**: Probed through `yt-dlp` extraction; fails with an explanatory `HtmlNotMediaError` if the page is pure HTML with no extractable streams.

---

## 4. Architecture Overview

The GUI stays strictly isolated from network, media-extraction, file-system collision, and SQLite code through clean layered modules under `src/link_downloader/`:

```text
src/link_downloader/
├── main.py & application.py    # CLI flags (--version, --self-test, --debug), logging, QApplication setup
├── core/                       # Enums, typed exceptions, dataclasses, Qt signals, URL/SSRF validators
├── platform/                   # platformdirs paths, OS file/folder open & reveal, desktop integration
├── config/                     # AppSettings defaults & atomic JSON SettingsManager
├── database/                   # Thread-safe SQLite WAL connection, schema migrations, HistoryRepository
├── engines/                    # BaseDownloadEngine, YtDlpEngine, DirectHttpEngine, UrlCapabilityResolver
├── services/                   # DownloadManager, QueueService, MetadataService, FileService, FfmpegService,
│                               # DependencyService, LegacyMigrationService
├── workers/                    # QRunnable MetadataWorker & DownloadWorker for QThreadPool execution
└── ui/                         # MainWindow, QSS theme engine, pages (Download/Queue/History/Settings),
                                # reusable cards, and DiagnosticDialog
```

Engine resolution flow:

```text
User URL -> normalize_and_validate_url()
         -> Specialized yt-dlp extractor? -> Yes -> YtDlpEngine
         -> HTTP HEAD/GET headers: HTML?  -> No  -> DirectHttpEngine (streaming .part + Range resume)
                                          -> Yes -> YtDlpEngine generic probe (or HtmlNotMediaError)
```

---

## 5. System Requirements

- **Python**: 3.11–3.15 (developed and verified on **Python 3.12**)
- **Operating Systems**:
  - Windows 10 / 11 (x86_64)
  - macOS (Apple Silicon `arm64` and Intel `x86_64` where supported by Qt 6 / PySide6)
  - Linux x86_64 (Ubuntu, Debian, Linux Mint, Fedora, Arch Linux) with Qt 6 system libraries (`libGL`, `libEGL`, `libxkbcommon`, `libxcb-cursor0` on X11/Wayland)
- **Recommended External Tools**:
  - **FFmpeg & FFprobe**: Required for merging separate adaptive video+audio streams (e.g., 1080p/4K MP4) and MP3 audio extraction.
  - **JavaScript Runtime (`deno` ≥ 2.3, `node` ≥ 22, or `quickjs`) + `yt-dlp-ejs`**: Required by modern `yt-dlp` for full YouTube extraction compatibility.

---

## 6. Installation & Running on Windows

```powershell
git clone https://github.com/livelyfun/youtube-video-downloader.git
cd youtube-video-downloader

py -3.12 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev,build]"

# Launch GUI
python scripts\dev.py
# Or via entry point
link-downloader
```

---

## 7. Installation & Running on macOS

```bash
git clone https://github.com/livelyfun/youtube-video-downloader.git
cd youtube-video-downloader

brew install python@3.12 ffmpeg node
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,build]"

python scripts/dev.py
```

---

## 8. Installation & Running on Linux

**Install system media/Qt dependencies:**

- **Ubuntu / Debian / Linux Mint**:
  ```bash
  sudo apt update && sudo apt install -y python3.12 python3.12-venv ffmpeg nodejs libgl1 libegl1 libxkbcommon0 libxcb-cursor0
  ```
- **Fedora / RHEL**:
  ```bash
  sudo dnf install -y python3.12 ffmpeg-free nodejs mesa-libGL mesa-libEGL libxkbcommon xcb-util-cursor
  ```
- **Arch Linux**:
  ```bash
  sudo pacman -S --needed python ffmpeg nodejs mesa libxkbcommon xcb-util-cursor
  ```

**Create virtual environment and launch:**

```bash
git clone https://github.com/livelyfun/youtube-video-downloader.git
cd youtube-video-downloader

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,build]"

python scripts/dev.py
```

---

## 9. FFmpeg Setup

- `FfmpegService` inspects system `PATH`, common OS installation directories (`/usr/bin`, `/opt/homebrew/bin`, `C:\ffmpeg\bin`, `%LOCALAPPDATA%\Programs\ffmpeg\bin`), and bundled assets alongside the packaged executable (`ffmpeg/`, `bin/`).
- If FFmpeg is absent, Link Downloader displays a non-blocking warning banner, allows pre-merged single-file and direct HTTP downloads, and disables or cleanly warns when choosing formats that require muxing or MP3 transcoding.

---

## 10. yt-dlp & JavaScript Runtime Notes

- `yt-dlp` (`yt-dlp[default]` + `yt-dlp-ejs`) is invoked strictly through its Python API (`yt_dlp.YoutubeDL`), without scraping terminal stdout/stderr.
- `DependencyService.get_ytdlp_js_runtimes()` automatically detects available runtimes (`deno`, `node`, `quickjs`) and passes the dictionary expected by `yt-dlp` (`{"node": {"path": ...}}`), ensuring YouTube challenge solving works even when `deno` is not installed and `node` is present.
- `prefer_ipv4` (enabled by default in Settings) binds `httpx` and `yt-dlp` sockets cleanly to `0.0.0.0` (`AF_INET`) to avoid stalls on networks with broken outbound IPv6 routing.

---

## 11. Building & Packaging

Build standalone bundles locally using `scripts/build.py` (defaults to `pyinstaller`; also supports `--packager pyside6-deploy` and `--packager nuitka` when installed):

```bash
source .venv/bin/activate
python scripts/build.py
```

Platform outputs produced in `dist/`:
- **Linux**: `dist/link-downloader/`, portable `dist/link-downloader-2.0.0-linux-x86_64.tar.gz`, `dist/AppDir/` (+ `.AppImage` if `appimagetool` is installed), `dist/link-downloader_2.0.0_amd64.deb`, and `dist/rpm/link-downloader.spec` (+ `.rpm` if `rpmbuild` is installed).
- **Windows** (built natively or via CI): `dist/link-downloader/link-downloader.exe` and `dist/link-downloader-2.0.0-windows-x86_64.zip`.
- **macOS** (built natively or via CI): `dist/Link Downloader.app` and `.dmg` (when `hdiutil` is available).

CI workflows in `.github/workflows/tests.yml` and `.github/workflows/build-release.yml` automate native cross-platform testing and builds across Ubuntu, Windows, and macOS (arm64 & x86_64).

---

## 12. Running Tests

```bash
# Lint source, tests, and packaging scripts
ruff check src tests scripts

# Run unit, security, HTTP/yt-dlp integration, and pytest-qt GUI tests
QT_QPA_PLATFORM=offscreen pytest -v

# Run full automated pipeline (ruff + pytest + PyInstaller build + binary --self-test)
QT_QPA_PLATFORM=offscreen python scripts/verify.py
```

---

## 13. Configuration & Data Locations

Paths resolve via `platformdirs` (and can be overridden with `LINK_DOWNLOADER_{CONFIG,DATA,CACHE,LOG,LEGACY}_DIR` environment variables):

- **Linux**: `~/.config/Link Downloader/settings.json`, `~/.local/share/Link Downloader/history.db`, `~/.local/state` or cache/logs under `platformdirs.user_log_dir("Link Downloader")`.
- **macOS**: `~/Library/Application Support/Link Downloader/`.
- **Windows**: `%APPDATA%\Link Downloader\` / `%LOCALAPPDATA%\Link Downloader\`.

---

## 14. Migration from Legacy Electron Version

On startup, `LegacyMigrationService` inspects `~/.config/yt-downloader/` (without deleting original files):

- Creates `.bak` backups alongside legacy `config.json` and `history.json` when absent.
- Maps camelCase Electron config keys (`downloadFolder`, `defaultFormat`, `defaultQuality`, `autoConvertMp3`, `concurrentDownloads`, `theme`) to `settings.json` once.
- Imports legacy `history.json` rows idempotently into SQLite `history.db` (`INSERT OR IGNORE`), mapping stale `"in-progress"` entries to `"cancelled"`.

---

## 15. Troubleshooting

- **Stalled or timing-out connections on dual-stack ISPs**: Keep **Prefer IPv4 networking** enabled in **Settings**.
- **YouTube extraction errors ("n challenge" or missing formats)**: Verify `yt-dlp-ejs` and `node` (≥ 22) or `deno` (≥ 2.3) appear as available in **Settings -> Diagnostic Report...**.
- **1080p/4K or MP3 options unavailable**: Install FFmpeg and click **Re-check** in **Settings**.
- **Headless / SSH / Wayland CI execution**: Set `QT_QPA_PLATFORM=offscreen` when running tests or `--self-test`.

---

## 16. Security & Privacy Notes

- **URL & SSRF Protection**: Only `http://` and `https://` URLs without embedded credentials are permitted; `localhost`, `.local`, `.internal`, loopback, RFC-1918 private networks, link-local / cloud metadata (`169.254.169.254`), and IPv4-mapped IPv6 addresses are blocked upfront and re-validated across every HTTP redirect hop (`follow_redirects=False`).
- **Path Traversal Prevention**: Filenames from URLs, `Content-Disposition`, and media titles are stripped of directory segments, Windows reserved device names (`CON`, `PRN`, `NUL`, `COM1`–`LPT9`), and control characters, then collision-resolved strictly within the configured destination directory.
- **No Telemetry or Remote Backend**: Zero analytics, remote tracking, or bundled server processes.

---

## 17. Known Limitations & Responsible Use

- Native Windows (`.exe`/`.zip`) and macOS (`.app`/`.dmg`) binaries cannot be compiled locally on Linux and are built natively on Windows/macOS runners via GitHub Actions; Authenticode and Apple notarization require repository signing secrets and are left unsigned by default.
- `.rpm` binary emission requires `rpmbuild` on the build host; when absent, the `.spec` file is generated alongside the standalone bundle.
- Use Link Downloader strictly in compliance with applicable copyright laws, website terms of service, and creator permissions. Only download content you own, have explicit permission to save, or that is legally permitted for offline access.
