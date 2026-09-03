const { contextBridge, ipcRenderer } = require('electron');
const { IPC } = require('../shared/ipcChannels');

contextBridge.exposeInMainWorld('electronAPI', {
  // Dependency check & Auto-install
  checkDeps: () => ipcRenderer.invoke(IPC.CHECK_DEPS),
  installYtdlp: () => ipcRenderer.invoke(IPC.INSTALL_YTDLP),
  onInstallProgress: (cb) => {
    const handler = (_, data) => cb(data);
    ipcRenderer.on('install-ytdlp-progress', handler);
    return () => ipcRenderer.removeListener('install-ytdlp-progress', handler);
  },

  // Config
  getConfig: () => ipcRenderer.invoke(IPC.GET_CONFIG),
  saveConfig: (config) => ipcRenderer.invoke(IPC.SAVE_CONFIG, config),

  // History
  getHistory: () => ipcRenderer.invoke(IPC.GET_HISTORY),
  clearHistory: () => ipcRenderer.invoke(IPC.CLEAR_HISTORY),

  // Fetch info
  fetchInfo: (url) => ipcRenderer.invoke(IPC.FETCH_INFO, { url }),

  // Download
  startDownload: (opts) => ipcRenderer.invoke(IPC.START_DOWNLOAD, opts),
  cancelDownload: (downloadId) => ipcRenderer.invoke('cancel-download', { downloadId }),

  // Open folder / file
  openFolder: (folderPath) => ipcRenderer.invoke(IPC.OPEN_FOLDER, folderPath),
  showItemInFolder: (filePath) => ipcRenderer.invoke('show-item-in-folder', filePath),

  // Event listeners
  onDownloadProgress: (cb) => {
    const handler = (_, data) => cb(data);
    ipcRenderer.on(IPC.DOWNLOAD_PROGRESS, handler);
    return () => ipcRenderer.removeListener(IPC.DOWNLOAD_PROGRESS, handler);
  },
  onDownloadComplete: (cb) => {
    const handler = (_, data) => cb(data);
    ipcRenderer.on(IPC.DOWNLOAD_COMPLETE, handler);
    return () => ipcRenderer.removeListener(IPC.DOWNLOAD_COMPLETE, handler);
  },
  onDownloadError: (cb) => {
    const handler = (_, data) => cb(data);
    ipcRenderer.on(IPC.DOWNLOAD_ERROR, handler);
    return () => ipcRenderer.removeListener(IPC.DOWNLOAD_ERROR, handler);
  },
});
