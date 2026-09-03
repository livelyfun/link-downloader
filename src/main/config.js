const { app } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');

const CONFIG_DIR = path.join(os.homedir(), '.config', 'yt-downloader');
const CONFIG_FILE = path.join(CONFIG_DIR, 'config.json');

const DEFAULT_CONFIG = {
  downloadFolder: path.join(os.homedir(), 'Downloads', 'yt-downloads'),
  defaultFormat: 'bestvideo+bestaudio/best',
  defaultQuality: 'best',
  autoConvertMp3: false,
  concurrentDownloads: 1,
  theme: 'dark',
};

function ensureConfigDir() {
  if (!fs.existsSync(CONFIG_DIR)) {
    fs.mkdirSync(CONFIG_DIR, { recursive: true });
  }
}

function loadConfig() {
  ensureConfigDir();
  if (!fs.existsSync(CONFIG_FILE)) {
    saveConfig(DEFAULT_CONFIG);
    return { ...DEFAULT_CONFIG };
  }
  try {
    const raw = fs.readFileSync(CONFIG_FILE, 'utf-8');
    return { ...DEFAULT_CONFIG, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

function saveConfig(config) {
  ensureConfigDir();
  const merged = { ...DEFAULT_CONFIG, ...config };
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(merged, null, 2), 'utf-8');
  return merged;
}

function ensureDownloadFolder(config) {
  const folder = config.downloadFolder || DEFAULT_CONFIG.downloadFolder;
  if (!fs.existsSync(folder)) {
    fs.mkdirSync(folder, { recursive: true });
  }
}

module.exports = { loadConfig, saveConfig, ensureDownloadFolder, DEFAULT_CONFIG, CONFIG_DIR };
