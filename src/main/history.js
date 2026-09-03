const fs = require('fs');
const path = require('path');
const os = require('os');

const HISTORY_FILE = path.join(os.homedir(), '.config', 'yt-downloader', 'history.json');

function ensureHistoryDir() {
  const dir = path.dirname(HISTORY_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function loadHistory() {
  ensureHistoryDir();
  if (!fs.existsSync(HISTORY_FILE)) return [];
  try {
    return JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf-8')) || [];
  } catch {
    return [];
  }
}

function saveHistory(history) {
  ensureHistoryDir();
  // Keep last 100 entries
  const trimmed = history.slice(-100);
  fs.writeFileSync(HISTORY_FILE, JSON.stringify(trimmed, null, 2), 'utf-8');
}

function addHistoryEntry(entry) {
  const history = loadHistory();
  const existing = history.findIndex(h => h.id === entry.id);
  if (existing >= 0) {
    history[existing] = entry;
  } else {
    history.push(entry);
  }
  saveHistory(history);
}

function updateHistoryEntry(id, updates) {
  const history = loadHistory();
  const idx = history.findIndex(h => h.id === id);
  if (idx >= 0) {
    history[idx] = { ...history[idx], ...updates };
    saveHistory(history);
    return history[idx];
  }
  return null;
}

function clearHistory() {
  saveHistory([]);
}

module.exports = { loadHistory, addHistoryEntry, updateHistoryEntry, clearHistory };
