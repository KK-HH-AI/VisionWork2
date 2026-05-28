import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import path from 'path';
import fs from 'fs';
import { spawn, ChildProcess } from 'child_process';
import crypto from 'crypto';
import net from 'net';

// ---- 状态变量 ----
let mainWindow: BrowserWindow | null;
let pythonProcess: ChildProcess | null;
let backendPort: number;
let backendToken: string;
let isBackendReady = false;
let viteProcess: ChildProcess | null;

// 判断是否已打包为生产环境
const IS_PACKAGED = app.isPackaged;

// ==============================
//  工具函数
// ==============================

/** 查找一个可用的本地回环端口 */
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

/**
 * 启动 Python 后端 (dev 用 python 命令, production 用打包好的 .exe)
 */
function startPythonBackend(port: number, token: string): Promise<void> {
  return new Promise((resolve, reject) => {
    let cmd: string;
    let args: string[];
    let cwd: string | undefined;

    if (IS_PACKAGED) {
      // ---------- 生产模式：使用 PyInstaller 打包好的 backend.exe ----------
      cmd = path.join(process.resourcesPath, 'backend', 'backend.exe');
      args = ['--port', String(port), '--token', token];
    } else {
      // ---------- 开发模式：使用系统的 python 解释器 ----------
      cmd = process.env.PYTHON_PATH || 'python';
      const scriptPath = path.join(__dirname, '..', 'src', 'backend', 'main.py');
      args = [scriptPath, '--port', String(port), '--token', token];
    }

    console.log(`[Main] Starting backend: ${cmd} ${args.join(' ')}`);

    pythonProcess = spawn(cmd, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      cwd,
    });

    let backendOutput = '';

    const onData = (data: Buffer) => {
      const str = data.toString();
      backendOutput += str;
      console.log(`[Backend] ${str.trim()}`);
      if (str.includes('Backend starting') || str.includes('Uvicorn running')) {
        isBackendReady = true;
        resolve();
      }
    };

    pythonProcess.stdout?.on('data', onData);
    pythonProcess.stderr?.on('data', onData);

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
    }, 30000);
  });
}

// ==============================
//  开发模式：启动 Vite 开发服务器
// ==============================
async function startViteDevServer(): Promise<number> {
  const vitePort = await findAvailablePort();

  return new Promise((resolve, reject) => {
    const frontendDir = path.join(__dirname, '..', 'src', 'frontend');
    viteProcess = spawn(
      process.platform === 'win32' ? 'npx.cmd' : 'npx',
      ['vite', '--port', String(vitePort), '--strictPort'],
      {
        cwd: frontendDir,
        stdio: ['pipe', 'pipe', 'pipe'],
        shell: true,
        env: { ...process.env, NO_COLOR: '1' },
      }
    );

    viteProcess.stdout?.on('data', (data: Buffer) => {
      console.log(`[Vite] ${data.toString().trim()}`);
    });
    viteProcess.stderr?.on('data', (data: Buffer) => {
      console.error(`[Vite Error] ${data.toString().trim()}`);
    });
    viteProcess.on('error', (err: Error) => {
      reject(err);
    });
    viteProcess.on('exit', (code) => {
      console.log(`[Vite] Process exited with code ${code}`);
    });

    const checkInterval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:${vitePort}`);
        if (res.ok || res.status === 200 || res.status === 304) {
          clearInterval(checkInterval);
          clearTimeout(timeout);
          console.log(`[Main] Vite is ready on port ${vitePort}`);
          resolve(vitePort);
        }
      } catch { /* 继续等待 */ }
    }, 500);

    const timeout = setTimeout(() => {
      clearInterval(checkInterval);
      reject(new Error('Vite startup timeout'));
    }, 30000);
  });
}

// ==============================
//  创建窗口 & 启动后端
// ==============================
async function createWindow() {
  try {
    if (IS_PACKAGED) {
      // ==================== 生产模式 ====================
      // 启动 Python 后端
      backendPort = await findAvailablePort();
      backendToken = crypto.randomBytes(16).toString('hex');
      console.log(`[Main] Starting backend on port ${backendPort}...`);
      await startPythonBackend(backendPort, backendToken);
      isBackendReady = true;
      console.log('[Main] Backend is ready');
      await new Promise(resolve => setTimeout(resolve, 500));

      // 创建窗口，加载打包好的前端静态文件
      mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        webPreferences: {
          nodeIntegration: false,
          contextIsolation: true,
          preload: path.join(__dirname, 'preload.js'),
          devTools: false,
        },
      });

      // 加载 Vite 构建产物 (dist/index.html)
      const indexPath = path.join(__dirname, '..', 'dist', 'index.html');
      mainWindow.loadFile(indexPath);

      mainWindow.on('closed', () => { mainWindow = null; });

    } else {
      // ==================== 开发模式 ====================
      console.log('[Main] Starting Vite dev server...');
      const vitePort = await startViteDevServer();
      console.log(`[Main] Vite is ready on port ${vitePort}`);

      backendPort = await findAvailablePort();
      backendToken = crypto.randomBytes(16).toString('hex');
      console.log(`[Main] Starting backend on port ${backendPort}...`);
      await startPythonBackend(backendPort, backendToken);
      isBackendReady = true;
      console.log('[Main] Backend is ready');
      await new Promise(resolve => setTimeout(resolve, 500));

      mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        webPreferences: {
          nodeIntegration: false,
          contextIsolation: true,
          preload: path.join(__dirname, 'preload.js'),
          devTools: false,
        },
      });

      mainWindow.loadURL(`http://localhost:${vitePort}`);
      mainWindow.on('closed', () => { mainWindow = null; });
    }
  } catch (err) {
    console.error(`[Main] Failed to start application: ${(err as Error).message}`);
    dialog.showErrorBox(
      '启动失败',
      IS_PACKAGED
        ? `无法启动后端服务：${(err as Error).message}`
        : `无法启动后端服务：${(err as Error).message}\n\n请检查Python环境是否正确安装。`
    );
    app.quit();
  }
}

// ==============================
//  优雅关闭
// ==============================
async function shutdownAll() {
  // 关闭 Python 后端
  if (pythonProcess) {
    console.log('[Main] Shutting down backend...');
    if (pythonProcess.exitCode === null) {
      pythonProcess.kill('SIGTERM');
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

  // 关闭 Vite (仅开发模式)
  if (viteProcess) {
    console.log('[Main] Shutting down Vite...');
    if (viteProcess.exitCode === null) {
      viteProcess.kill('SIGTERM');
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          viteProcess!.kill('SIGKILL');
          resolve();
        }, 3000);
        viteProcess!.on('exit', () => {
          clearTimeout(timeout);
          resolve();
        });
      });
    }
    viteProcess = null;
    console.log('[Main] Vite shutdown complete');
  }
}

// ==============================
//  Electron 生命周期
// ==============================
app.whenReady().then(createWindow);

app.on('window-all-closed', async () => {
  await shutdownAll();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', async (event) => {
  if (pythonProcess && pythonProcess.exitCode === null) {
    event.preventDefault();
    await shutdownAll();
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// ==============================
//  IPC 接口
// ==============================
ipcMain.handle('get-backend-config', () => {
  return { port: backendPort, token: backendToken, ready: isBackendReady };
});

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow!, {
    properties: ['openDirectory'],
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