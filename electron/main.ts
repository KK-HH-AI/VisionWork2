import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import path from 'path';
import fs from 'fs';
import { spawn, ChildProcess } from 'child_process';
import crypto from 'crypto';
import http from 'http';
import net from 'net';

let mainWindow: BrowserWindow | null;
let pythonProcess: ChildProcess | null;
let backendPort: number;
let backendToken: string;
let isBackendReady = false;

function findAvailablePort(): Promise<number> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address();
      const port = typeof addr === 'object' && addr ? addr.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function waitForBackendReady(port: number, timeout = 10000): Promise<void> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    const checkInterval = setInterval(() => {
      if (Date.now() - startTime > timeout) {
        clearInterval(checkInterval);
        reject(new Error(`Backend did not become ready within ${timeout}ms`));
        return;
      }
      http.get(`http://127.0.0.1:${port}/docs`, (res) => {
        if (res.statusCode === 200) {
          clearInterval(checkInterval);
          isBackendReady = true;
          console.log('[Backend] Backend is ready');
          resolve();
        }
      }).on('error', () => {});
    }, 500);
  });
}

function startPythonBackend(port: number, token: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const pythonPath = process.env.PYTHON_PATH || 'python';
    const scriptPath = path.join(__dirname, '..', 'src', 'backend', 'main.py');

    pythonProcess = spawn(pythonPath, [scriptPath, '--port', String(port), '--token', token], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    });

    let backendOutput = '';

    pythonProcess.stdout?.on('data', (data: Buffer) => {
      const str = data.toString();
      backendOutput += str;
      console.log(`[Backend] ${str.trim()}`);
      if (str.includes('Backend starting') || str.includes('Uvicorn running')) {
        resolve();
      }
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
      const str = data.toString();
      backendOutput += str;
      console.error(`[Backend Error] ${str.trim()}`);
    });

    pythonProcess.on('error', (err: Error) => {
      console.error(`[Backend] Failed to start: ${err.message}`);
      reject(err);
    });

    pythonProcess.on('exit', (code: number | null) => {
      console.log(`[Backend] Process exited with code ${code}`);
      isBackendReady = false;
      if (code !== 0 && code !== null) {
        console.error(`[Backend] Abnormal exit. Output:\n${backendOutput}`);
      }
      if (mainWindow) {
        mainWindow.webContents.send('backend-exited', { code });
      }
    });

    setTimeout(() => {
      if (!isBackendReady) {
        reject(new Error('Backend startup timeout'));
      }
    }, 15000);
  });
}

async function createWindow() {
  try {
    backendPort = await findAvailablePort();
    backendToken = crypto.randomBytes(16).toString('hex');

    console.log(`[Main] Starting backend on port ${backendPort}...`);
    await startPythonBackend(backendPort, backendToken);

    console.log('[Main] Waiting for backend to be ready...');
    await waitForBackendReady(backendPort);

    await new Promise(resolve => setTimeout(resolve, 500));

    mainWindow = new BrowserWindow({
      width: 1400,
      height: 900,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        preload: path.join(__dirname, 'preload.js')
      }
    });

    const isDev = true;

    if (isDev || process.env.NODE_ENV === 'development' || process.env.VITE_DEV_SERVER_URL) {
      mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173');
      mainWindow.webContents.openDevTools();
    } else {
      mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
    }

    mainWindow.on('closed', () => {
      mainWindow = null;
    });
  } catch (err) {
    console.error(`[Main] Failed to start application: ${(err as Error).message}`);
    dialog.showErrorBox('启动失败', `无法启动后端服务：${(err as Error).message}\n\n请检查Python环境是否正确安装。`);
    app.quit();
  }
}

async function shutdownBackend() {
  if (!pythonProcess) {
    return;
  }

  console.log('[Main] Shutting down backend...');

  if (pythonProcess.exitCode === null) {
    if (process.platform === 'win32') {
      pythonProcess.kill('SIGTERM');
    } else {
      pythonProcess.kill('SIGTERM');
    }

    await new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        console.log('[Main] Backend did not exit gracefully, force killing...');
        pythonProcess!.kill('SIGKILL');
        resolve();
      }, 3000);

      pythonProcess!.on('exit', () => {
        clearTimeout(timeout);
        resolve();
      });
    });
  }

  pythonProcess = null;
  isBackendReady = false;
  console.log('[Main] Backend shutdown complete');
}

app.whenReady().then(createWindow);

app.on('window-all-closed', async () => {
  await shutdownBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', async (event) => {
  if (pythonProcess && pythonProcess.exitCode === null) {
    event.preventDefault();
    await shutdownBackend();
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

ipcMain.handle('get-backend-config', () => {
  console.log(`[Main] get-backend-config called: port=${backendPort}, token=${backendToken}, ready=${isBackendReady}`);
  return { port: backendPort, token: backendToken, ready: isBackendReady };
});

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow!, {
    properties: ['openDirectory']
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});

ipcMain.handle('read-file', async (_event, filePath: string) => {
  try {
    if (!fs.existsSync(filePath)) {
      return { success: false, error: '文件不存在' };
    }
    const stat = fs.statSync(filePath);
    if (stat.size > 5 * 1024 * 1024) {
      return { success: false, error: '文件过大（超过5MB）' };
    }
    const content = fs.readFileSync(filePath, 'utf-8');
    return { success: true, content, size: stat.size };
  } catch (err) {
    return { success: false, error: (err as Error).message };
  }
});
