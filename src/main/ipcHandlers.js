const { ipcMain, shell } = require('electron');
const { IPC } = require('../shared/ipcChannels');
const { fetchVideoInfo, startDownload, checkDependencies, downloadYtDlpBinary } = require('./ytdlp');
const { loadConfig, saveConfig, ensureDownloadFolder } = require('./config');
const { loadHistory, addHistoryEntry, updateHistoryEntry, clearHistory } = require('./history');
const { randomUUID } = require('crypto');
const path = require('path');
const fs = require('fs');

const activeDownloads = new Map();

function registerIpcHandlers(mainWindow) {
  // ── Dependency check & Auto-install ─────────────────
  ipcMain.handle(IPC.CHECK_DEPS, async () => {
    return checkDependencies();
  });

  ipcMain.handle(IPC.INSTALL_YTDLP, async () => {
    try {
      await downloadYtDlpBinary((percent) => {
        mainWindow.webContents.send('install-ytdlp-progress', { percent });
      });
      return { success: true };
    } catch (err) {
      return { success: false, error: err.message };
    }
  });

  // ── Config ───────────────────────────────────────────
  ipcMain.handle(IPC.GET_CONFIG, () => loadConfig());

  ipcMain.handle(IPC.SAVE_CONFIG, (_, config) => {
    return saveConfig(config);
  });

  // ── History ──────────────────────────────────────────
  ipcMain.handle(IPC.GET_HISTORY, () => loadHistory());

  ipcMain.handle(IPC.CLEAR_HISTORY, () => {
    clearHistory();
    return true;
  });

  // ── Fetch video info ─────────────────────────────────
  ipcMain.handle(IPC.FETCH_INFO, async (_, { url }) => {
    try {
      const info = await fetchVideoInfo(url);
      return { success: true, data: info };
    } catch (err) {
      return { success: false, error: err.message };
    }
  });

  // ── Start download ───────────────────────────────────
  ipcMain.handle(IPC.START_DOWNLOAD, async (_, { url, formatId, title }) => {
    const config = loadConfig();
    ensureDownloadFolder(config);

    const downloadId = randomUUID();

    const historyEntry = {
      id: downloadId,
      url,
      title: title || url,
      formatId,
      status: 'in-progress',
      percent: 0,
      speed: null,
      eta: null,
      filePath: null,
      error: null,
      startedAt: new Date().toISOString(),
      completedAt: null,
    };

    addHistoryEntry(historyEntry);

    mainWindow.webContents.send(IPC.DOWNLOAD_PROGRESS, { downloadId, percent: 0, status: 'in-progress', title: historyEntry.title });

    const handle = startDownload({
      url,
      formatId,
      downloadFolder: config.downloadFolder,
      autoConvertMp3: config.autoConvertMp3,
      onProgress: ({ percent, speed, eta, size }) => {
        const update = { id: downloadId, percent, speed, eta, size, status: 'in-progress' };
        updateHistoryEntry(downloadId, update);
        mainWindow.webContents.send(IPC.DOWNLOAD_PROGRESS, {
          downloadId, percent, speed, eta, size, status: 'in-progress', title: historyEntry.title,
        });
      },
      onComplete: ({ filePath }) => {
        const completedAt = new Date().toISOString();
        updateHistoryEntry(downloadId, { status: 'completed', percent: 100, filePath, completedAt });
        activeDownloads.delete(downloadId);
        mainWindow.webContents.send(IPC.DOWNLOAD_COMPLETE, {
          downloadId, filePath, title: historyEntry.title, status: 'completed',
        });
      },
      onError: (err) => {
        updateHistoryEntry(downloadId, { status: 'failed', error: err.message });
        activeDownloads.delete(downloadId);
        mainWindow.webContents.send(IPC.DOWNLOAD_ERROR, {
          downloadId, error: err.message, title: historyEntry.title, status: 'failed',
        });
      },
    });

    activeDownloads.set(downloadId, handle);
    return { downloadId };
  });

  // ── Cancel download ──────────────────────────────────
  ipcMain.handle('cancel-download', (_, { downloadId }) => {
    const handle = activeDownloads.get(downloadId);
    if (handle) {
      handle.cancel();
      activeDownloads.delete(downloadId);
      updateHistoryEntry(downloadId, { status: 'cancelled' });
      return true;
    }
    return false;
  });

  // ── Open folder ──────────────────────────────────────
  ipcMain.handle(IPC.OPEN_FOLDER, (_, folderPath) => {
    shell.openPath(folderPath);
  });

  // ── Open file in folder ──────────────────────────────
  ipcMain.handle('show-item-in-folder', (_, filePath) => {
    if (filePath && fs.existsSync(filePath)) {
      shell.showItemInFolder(filePath);
    } else {
      const config = loadConfig();
      shell.openPath(config.downloadFolder);
    }
  });
}

module.exports = { registerIpcHandlers };
