const { app, BrowserWindow, nativeTheme } = require('electron');
const path = require('path');
const { registerIpcHandlers } = require('./ipcHandlers');

// Keep a global reference to avoid garbage collection
let mainWindow;

const isDev = !app.isPackaged;
const VITE_DEV_PORT = 5173;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 780,
    minWidth: 800,
    minHeight: 600,
    frame: true,
    backgroundColor: '#0f0f13',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
    icon: path.join(__dirname, '../../build/icon.png'),
    title: 'YT Downloader',
    show: false, // show after ready-to-show to avoid flash
  });

  // Load app
  if (isDev) {
    mainWindow.loadURL(`http://localhost:${VITE_DEV_PORT}`);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '../../dist/renderer/index.html'));
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  registerIpcHandlers(mainWindow);
}

app.whenReady().then(() => {
  // Force dark title bar on Linux
  nativeTheme.themeSource = 'dark';
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
