// SellHub — десктопная оболочка (Electron).
// Загружает ту же панель, что и сайт (frontend/index.html).
// Без сервера панель сама включает офлайн-демо-режим.
const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

function indexFile() {
  // В собранном приложении index.html лежит рядом с main.js (копия из frontend/),
  // при запуске из репозитория берём оригинал из ../frontend.
  const local = path.join(__dirname, 'index.html');
  return fs.existsSync(local) ? local : path.join(__dirname, '..', 'frontend', 'index.html');
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1000,
    minHeight: 640,
    backgroundColor: '#0d1017',
    title: 'SellHub — панель продавца',
    autoHideMenuBar: true,
  });
  win.loadFile(indexFile());
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
