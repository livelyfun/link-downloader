// Shared IPC channel constants
// Used by both main process and renderer to avoid string typos

const IPC = {
  // Info fetch
  FETCH_INFO: 'fetch-info',
  FETCH_INFO_REPLY: 'fetch-info-reply',

  // Download
  START_DOWNLOAD: 'start-download',
  DOWNLOAD_PROGRESS: 'download-progress',
  DOWNLOAD_COMPLETE: 'download-complete',
  DOWNLOAD_ERROR: 'download-error',

  // History
  GET_HISTORY: 'get-history',
  CLEAR_HISTORY: 'clear-history',
  HISTORY_DATA: 'history-data',

  // Config / Settings
  GET_CONFIG: 'get-config',
  SAVE_CONFIG: 'save-config',
  CONFIG_DATA: 'config-data',

  // Dependency check & Auto-install
  CHECK_DEPS: 'check-deps',
  DEPS_RESULT: 'deps-result',
  INSTALL_YTDLP: 'install-ytdlp',

  // Open folder in file manager
  OPEN_FOLDER: 'open-folder',
};

module.exports = { IPC };
