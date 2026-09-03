const { execFile, spawn } = require('child_process');
const { promisify } = require('util');
const path = require('path');
const fs = require('fs');
const os = require('os');
const https = require('https');

const execFileAsync = promisify(execFile);

// ─────────────────────────────────────────────
// Executable Path Resolution
// ─────────────────────────────────────────────
function getYtDlpPath() {
  const customBin = path.join(os.homedir(), '.config', 'yt-downloader', 'bin', 'yt-dlp');
  const localBin = path.join(os.homedir(), '.local', 'bin', 'yt-dlp');

  if (fs.existsSync(customBin)) return customBin;
  if (fs.existsSync(localBin)) return localBin;
  if (fs.existsSync('/usr/local/bin/yt-dlp')) return '/usr/local/bin/yt-dlp';
  if (fs.existsSync('/usr/bin/yt-dlp')) return '/usr/bin/yt-dlp';

  return 'yt-dlp'; // fallback to PATH
}

function getFfmpegPath() {
  const localBin = path.join(os.homedir(), '.local', 'bin', 'ffmpeg');
  if (fs.existsSync(localBin)) return localBin;
  if (fs.existsSync('/usr/local/bin/ffmpeg')) return '/usr/local/bin/ffmpeg';
  if (fs.existsSync('/usr/bin/ffmpeg')) return '/usr/bin/ffmpeg';

  return 'ffmpeg'; // fallback to PATH
}

// ─────────────────────────────────────────────
// URL validation
// ─────────────────────────────────────────────
const YT_URL_RE = /^https?:\/\/(www\.)?(youtube\.com\/(watch\?.*v=|shorts\/|embed\/)|youtu\.be\/).+/i;

function isValidYouTubeUrl(url) {
  if (!url || typeof url !== 'string') return false;
  return YT_URL_RE.test(url.trim());
}

// ─────────────────────────────────────────────
// Dependency detection & Auto-Installer
// ─────────────────────────────────────────────
async function checkDependencies() {
  const result = { ytdlp: false, ffmpeg: false, ytdlpVersion: null, ffmpegVersion: null, ytdlpPath: null };
  const ytBin = getYtDlpPath();
  const ffBin = getFfmpegPath();

  try {
    const { stdout: ytOut } = await execFileAsync(ytBin, ['--version']);
    result.ytdlp = true;
    result.ytdlpVersion = ytOut.trim();
    result.ytdlpPath = ytBin;
  } catch {
    result.ytdlp = false;
  }

  try {
    const { stderr: ffOut } = await execFileAsync(ffBin, ['-version']);
    result.ffmpeg = true;
    const match = ffOut.match(/ffmpeg version (\S+)/);
    result.ffmpegVersion = match ? match[1] : 'unknown';
  } catch {
    result.ffmpeg = false;
  }

  return result;
}

/**
 * Automatically download official yt-dlp binary from GitHub Releases into ~/.config/yt-downloader/bin/yt-dlp
 */
function downloadYtDlpBinary(onProgress) {
  return new Promise((resolve, reject) => {
    const binDir = path.join(os.homedir(), '.config', 'yt-downloader', 'bin');
    if (!fs.existsSync(binDir)) {
      fs.mkdirSync(binDir, { recursive: true });
    }
    const destPath = path.join(binDir, 'yt-dlp');

    const downloadUrl = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp';

    function fetchUrl(url) {
      https.get(url, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          return fetchUrl(res.headers.location);
        }
        if (res.statusCode !== 200) {
          return reject(new Error(`Failed to download yt-dlp binary (HTTP status ${res.statusCode})`));
        }

        const totalBytes = parseInt(res.headers['content-length'] || '0', 10);
        let downloadedBytes = 0;

        const fileStream = fs.createWriteStream(destPath);

        res.on('data', (chunk) => {
          downloadedBytes += chunk.length;
          if (totalBytes > 0 && onProgress) {
            onProgress(Math.round((downloadedBytes / totalBytes) * 100));
          }
        });

        res.pipe(fileStream);

        fileStream.on('finish', () => {
          fileStream.close(() => {
            try {
              fs.chmodSync(destPath, 0o755); // make executable
              resolve(destPath);
            } catch (err) {
              reject(err);
            }
          });
        });

        fileStream.on('error', (err) => {
          fs.unlink(destPath, () => {});
          reject(err);
        });
      }).on('error', (err) => {
        reject(err);
      });
    }

    fetchUrl(downloadUrl);
  });
}

// ─────────────────────────────────────────────
// Fetch metadata
// ─────────────────────────────────────────────
async function fetchVideoInfo(url) {
  if (!isValidYouTubeUrl(url)) {
    throw new Error('Invalid YouTube URL. Please paste a valid video link.');
  }

  const ytBin = getYtDlpPath();

  let raw;
  try {
    const { stdout } = await execFileAsync(
      ytBin,
      ['-J', '--no-warnings', '--skip-download', url.trim()],
      { timeout: 30000, maxBuffer: 50 * 1024 * 1024 }
    );
    raw = JSON.parse(stdout);
  } catch (err) {
    if (err.code === 'ENOENT') {
      throw new Error(`yt-dlp binary not found. Please click "Auto-Install yt-dlp" above or run: sudo apt install yt-dlp`);
    }
    if (err.killed) throw new Error('Metadata fetch timed out. Check your internet connection.');
    const msg = err.stderr || err.message || '';
    if (msg.includes('Private video')) throw new Error('This video is private and cannot be downloaded.');
    if (msg.includes('Video unavailable')) throw new Error('This video is unavailable.');
    if (msg.includes('age')) throw new Error('This video is age-restricted and cannot be accessed.');
    throw new Error(`Failed to fetch video info: ${msg.split('\n')[0]}`);
  }

  // Parse formats
  const formats = (raw.formats || [])
    .filter(f => f.vcodec !== 'none' || f.acodec !== 'none')
    .map(f => {
      const hasVideo = f.vcodec && f.vcodec !== 'none';
      const hasAudio = f.acodec && f.acodec !== 'none';
      let kind = 'video+audio';
      if (hasVideo && !hasAudio) kind = 'video-only';
      if (!hasVideo && hasAudio) kind = 'audio-only';

      const resolution = f.resolution || (f.height ? `${f.width || '?'}x${f.height}` : f.abr ? `${Math.round(f.abr)}kbps` : '?');
      const filesizeMb = f.filesize
        ? `${(f.filesize / 1024 / 1024).toFixed(1)} MB`
        : f.filesize_approx
        ? `~${(f.filesize_approx / 1024 / 1024).toFixed(1)} MB`
        : 'unknown size';

      return {
        id: f.format_id,
        ext: f.ext,
        kind,
        resolution,
        vcodec: hasVideo ? f.vcodec : null,
        acodec: hasAudio ? f.acodec : null,
        fps: f.fps || null,
        filesize: filesizeMb,
        tbr: f.tbr || null,
        abr: f.abr || null,
        vbr: f.vbr || null,
        label: `${kind === 'audio-only' ? '🎵' : kind === 'video-only' ? '🎬' : '🎥'} ${resolution} · ${f.ext.toUpperCase()} · ${filesizeMb}`,
      };
    })
    .sort((a, b) => {
      const kindOrder = { 'video+audio': 0, 'video-only': 1, 'audio-only': 2 };
      const ka = kindOrder[a.kind] ?? 3;
      const kb = kindOrder[b.kind] ?? 3;
      if (ka !== kb) return ka - kb;
      const ra = parseInt(a.resolution) || 0;
      const rb = parseInt(b.resolution) || 0;
      return rb - ra;
    });

  // Add a "Best (auto)" option at the top
  formats.unshift({
    id: 'bestvideo+bestaudio/best',
    ext: 'mp4',
    kind: 'video+audio',
    resolution: 'Best available',
    label: '⭐ Best Quality (auto-select)',
    filesize: 'varies',
  });

  // Add audio-only mp3 option
  formats.push({
    id: 'bestaudio/best',
    ext: 'mp3',
    kind: 'audio-only',
    resolution: 'Best audio',
    label: '🎵 Audio only (MP3 via ffmpeg)',
    filesize: 'varies',
  });

  const durationSec = raw.duration || 0;
  const durationStr = formatDuration(durationSec);

  return {
    id: raw.id,
    title: raw.title,
    thumbnail: raw.thumbnail,
    duration: durationStr,
    durationSec,
    uploader: raw.uploader,
    uploadDate: raw.upload_date,
    viewCount: raw.view_count,
    url: url.trim(),
    formats,
  };
}

function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ─────────────────────────────────────────────
// Download
// ─────────────────────────────────────────────
function startDownload({ url, formatId, downloadFolder, autoConvertMp3, onProgress, onComplete, onError }) {
  const ytBin = getYtDlpPath();

  const args = [
    '-f', formatId,
    '-o', path.join(downloadFolder, '%(title)s.%(ext)s'),
    '--newline',
    '--no-warnings',
  ];

  const ffBin = getFfmpegPath();
  if (ffBin !== 'ffmpeg' && fs.existsSync(ffBin)) {
    args.push('--ffmpeg-location', ffBin);
  }

  if (formatId === 'bestaudio/best' || autoConvertMp3) {
    args.push('--extract-audio', '--audio-format', 'mp3', '--audio-quality', '0');
  }

  if (formatId.includes('+')) {
    args.push('--merge-output-format', 'mp4');
  }

  args.push(url.trim());

  const proc = spawn(ytBin, args, { stdio: ['ignore', 'pipe', 'pipe'] });

  let lastLine = '';
  let destFile = null;

  const progressRe = /\[download\]\s+([\d.]+)%\s+of\s+([\d.]+\s*\S+)\s+at\s+([\d.]+\s*\S+\/s)\s+ETA\s+(\S+)/;
  const destRe = /\[(?:download|Merger|ExtractAudio)\]\s+Destination:\s+(.+)/;

  proc.stdout.on('data', (chunk) => {
    const text = chunk.toString();
    const lines = (lastLine + text).split('\n');
    lastLine = lines.pop();
    for (const line of lines) {
      const m = progressRe.exec(line);
      if (m) {
        onProgress({
          percent: parseFloat(m[1]),
          size: m[2].trim(),
          speed: m[3].trim(),
          eta: m[4].trim(),
          line: line.trim(),
        });
      }
      const dm = destRe.exec(line);
      if (dm) destFile = dm[1].trim();
    }
  });

  proc.stderr.on('data', (chunk) => {
    const text = chunk.toString();
    const lines = text.split('\n');
    for (const line of lines) {
      const m = progressRe.exec(line);
      if (m) {
        onProgress({ percent: parseFloat(m[1]), size: m[2]?.trim(), speed: m[3]?.trim(), eta: m[4]?.trim(), line: line.trim() });
      }
    }
  });

  proc.on('close', (code) => {
    if (code === 0) {
      onComplete({ filePath: destFile });
    } else if (code !== null) {
      onError(new Error(`yt-dlp exited with code ${code}. Check if video is available.`));
    }
  });

  proc.on('error', (err) => {
    if (err.code === 'ENOENT') {
      onError(new Error('yt-dlp binary not found. Click "Auto-Install yt-dlp" to download it automatically.'));
    } else {
      onError(err);
    }
  });

  return {
    cancel: () => proc.kill('SIGTERM'),
  };
}

module.exports = { fetchVideoInfo, startDownload, checkDependencies, downloadYtDlpBinary, isValidYouTubeUrl };
