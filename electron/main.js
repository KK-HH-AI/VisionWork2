const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const crypto = require('crypto');

let mainWindow;
let pythonProcess;
let backendPort;
let backendToken;

function findAvailablePort() {
  const net = require('net');
  return new Promise((resolve) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

function startPythonBackend(port, token) {
  return new Promise((resolve) => {
    const pythonPath = process.env.PYTHON_PATH || 'python';
    const scriptPath = path.join(__dirname, '..', 'src', 'backend', 'server.py');

    pythonProcess = spawn(pythonPath, [scriptPath, '--port', String(port), '--token', token], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    });

    const checkBackend = (data) => {
      const str = data.toString();
      console.log(`[Backend] ${str.trim()}`);
      if (str.includes('Backend starting') || str.includes('Uvicorn running')) {
        resolve();
      }
    };

    pythonProcess.stdout.on('data', checkBackend);
    pythonProcess.stderr.on('data', checkBackend);

    pythonProcess.on('error', (err) => {
      console.error(`[Backend Error] ${err.message}`);
      resolve();
    });

    pythonProcess.on('exit', (code) => {
      console.log(`[Backend] Process exited with code ${code}`);
    });

    setTimeout(() => resolve(), 3000);
  });
}

async function createWindow() {
  backendPort = await findAvailablePort();
  backendToken = crypto.randomBytes(16).toString('hex');

  await startPythonBackend(backendPort, backendToken);

  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  if (process.env.NODE_ENV === 'development' || process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

ipcMain.handle('get-backend-config', () => {
  return { port: backendPort, token: backendToken };
});

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  
  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});
