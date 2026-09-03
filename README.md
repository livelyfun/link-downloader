# YT Downloader (Debian Desktop App)

A modern, fast, local-only desktop application for downloading YouTube videos on Debian Linux (and Debian-based distributions like Ubuntu, Linux Mint, Pop!_OS). Built with Electron, React, Tailwind CSS, and powered by `yt-dlp`.

![YT Downloader Icon](./build/icon.png)

---

## Features

- **Metadata Extraction**: Fetch video title, thumbnail, duration, view count, and available resolutions/formats using `yt-dlp`.
- **Format Options**: Choose between combined (video + audio), video-only, or audio-only (MP3 conversion via `ffmpeg`).
- **Live Progress**: Real-time progress bar with download speed, ETA, and file size updates parsed directly from `yt-dlp` output.
- **Local Storage Config**: Custom download destination directory stored in `~/.config/yt-downloader/config.json`.
- **Download History**: Track past downloads stored locally in `~/.config/yt-downloader/history.json`.
- **Dependency Detection**: Automatic check for `yt-dlp` and `ffmpeg` on application launch with clear instructions if missing.
- **Debian Integration**: Packaged as a standard `.deb` installer with `.desktop` menu entry and declared package dependencies.

---

## Prerequisites (System Dependencies)

Before running or building the app, ensure `yt-dlp` and `ffmpeg` are installed on your machine.

### 1. Install via `apt` (Recommended on Debian / Ubuntu)
```bash
sudo apt update
sudo apt install -y python3 ffmpeg yt-dlp
```

### 2. Alternatively, install latest `yt-dlp` via `pip`
```bash
pip install -U yt-dlp
```

---

## Development Setup

To run the application locally in development mode:

1. **Clone or navigate to the project directory:**
   ```bash
   cd "youtube video downloader"
   ```

2. **Install Node.js dependencies:**
   ```bash
   npm install
   ```

3. **Start Vite renderer dev server:**
   In one terminal:
   ```bash
   npm run dev
   ```

4. **Launch Electron app:**
   In another terminal:
   ```bash
   npm start
   ```

---

## Building the `.deb` Package

To compile the React frontend and package the application into a standalone `.deb` installer for Debian Linux:

```bash
npm run build
```

This will run `vite build` followed by `electron-builder --linux deb`.

The compiled `.deb` package will be created under:
```
dist-package/youtube-video-downloader_1.0.0_amd64.deb
```

---

## Installing the `.deb` Package

Install the generated `.deb` package on any Debian-based distribution:

```bash
sudo dpkg -i dist-package/youtube-video-downloader_1.0.0_amd64.deb
sudo apt-get install -f # Fix any missing dependencies if prompted
```

Once installed, **YT Downloader** will be available in your desktop application launcher menu under **Utilities / Network**.

---

## Project Architecture

```
youtube video downloader/
├── build/
│   ├── icon.png                 # 512x512 App Icon
│   └── yt-downloader.desktop    # Linux desktop launcher entry
├── src/
│   ├── main/                    # Electron Main Process (Node.js)
│   │   ├── main.js              # Entry point & BrowserWindow lifecycle
│   │   ├── preload.js           # Safe contextBridge IPC API
│   │   ├── ipcHandlers.js       # Main process IPC request handlers
│   │   ├── ytdlp.js             # Child process wrapper for yt-dlp & ffmpeg
│   │   ├── config.js            # User config manager (~/.config/yt-downloader/config.json)
│   │   └── history.js           # Download history manager (~/.config/yt-downloader/history.json)
│   ├── renderer/                # Electron Renderer Process (React + Tailwind)
│   │   ├── index.html           # HTML container
│   │   ├── main.jsx             # React DOM entry
│   │   ├── index.css            # Tailwind & glassmorphism dark theme styles
│   │   ├── App.jsx              # Main tab layout & state management
│   │   └── components/
│   │       ├── UrlInput.jsx         # URL input & fetch button
│   │       ├── VideoInfoCard.jsx    # Metadata preview & format selector
│   │       ├── DownloadProgress.jsx # Real-time progress bar
│   │       ├── HistoryList.jsx      # Download history component
│   │       ├── Settings.jsx         # App settings & folder picker
│   │       └── DependencyCheck.jsx  # Dependency warning banner
│   └── shared/                  # Shared Constants & Types
│       └── ipcChannels.js       # Centralized IPC channel names
├── electron-builder.yml         # Packaging configuration for .deb target
├── tailwind.config.js           # Tailwind CSS configuration
├── vite.config.mjs              # Vite bundler configuration
└── package.json                 # Project dependencies & build scripts
```

---

## Configuration & Data Storage

All application configuration and history data are stored locally in standard XDG directory paths:

- **Config**: `~/.config/yt-downloader/config.json`
- **History**: `~/.config/yt-downloader/history.json`
- **Default Downloads Path**: `~/Downloads/yt-downloads/`
