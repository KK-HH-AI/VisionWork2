import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import path from 'path';
import fs from 'fs';
import { spawn, ChildProcess } from 'child_process';
import crypto from 'crypto';
import net from 'net';

let mainWindow: BrowserWindow | null;
let pythonProcess: ChildProcess | null;
let backendPort: number;
let backendToken: string;
let isBackendReady = false;//代表后端是否启动成功的标志
let viteProcess : ChildProcess | null;

/**
 * 查找当前可用的端口号
 * 创建一个临时服务器并监听0端口，系统会自动分配一个可用的端口号
 * @returns 返回一个Promise，解析值为可用的端口号
 */
function findAvailablePort(): Promise<number> {
  return new Promise((resolve) => {
    // 创建一个新的服务器实例
    const server = net.createServer();
    // 监听0端口，系统会自动分配一个可用的端口号
    // '127.0.0.1' 指定本地回环地址
    server.listen(0, '127.0.0.1', () => {
      // 获取服务器的地址信息
      const addr = server.address();
      // 提取端口号，处理地址对象可能为null的情况
      const port = typeof addr === 'object' && addr ? addr.port : 0;
      // 关闭服务器并返回获取到的端口号
      server.close(() => resolve(port));
    });
  });
}

/**
 * 启动 Python 后端服务
 * 根据端口和令牌启动 main.py 子进程，监听 stdout 判断启动完成
 * @param port - 后端监听端口
 * @param token - 认证令牌
 * @returns 启动成功时 resolve，进程出错或超时则 reject
 */
function startPythonBackend(port: number, token: string): Promise<void> {
  return new Promise((resolve, reject) => {
    //获得python的环境变量
    const pythonPath = process.env.PYTHON_PATH || 'python';
    //拼接后端主程序的文件路径
    const scriptPath = path.join(__dirname, '..', 'src', 'backend', 'main.py');

    //启动python后端进程，并设置python环境变量
    pythonProcess = spawn(pythonPath, [scriptPath, '--port', String(port), '--token', token], {
      stdio: ['pipe', 'pipe', 'pipe'],
      //PYTHONIOENCODING 是 Python 专用的一个环境变量，用来控制 Python 解释器输入输出（stdin/stdout/stderr）的编码。
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    });

    let backendOutput = '';

    //后端正常输出
    pythonProcess.stdout?.on('data', (data: Buffer) => {
      const str = data.toString();
      backendOutput += str;
      console.log(`[Backend] ${str.trim()}`);
      if (str.includes('Backend starting') || str.includes('Uvicorn running')) {
        isBackendReady = true;
        resolve();
      }
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
      const str = data.toString();
      backendOutput += str;
      console.error(`[Backend Error] ${str.trim()}`);
      if (str.includes('Backend starting') || str.includes('Uvicorn running')) {
        isBackendReady = true;
        resolve();
      }
    });

    //无法创建python子进程时
    pythonProcess.on('error', (err: Error) => {
      console.error(`[Backend] Failed to start: ${err.message}`);
      reject(err);
    });

    //监听后端进程是否退出
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
    
    //后端进程启动超过30s，任务启动失败
    setTimeout(() => {
      if (!isBackendReady) {
        reject(new Error('Backend startup timeout'));
      }
    }, 30000);
  });
}

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
      console.error(`[Vite] Failed to start: ${err.message}`);
      reject(err);
    });

    viteProcess.on('exit', (code: number | null) => {
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
      } catch {
        // 继续等待
      }
    }, 500);

    const timeout = setTimeout(() => {
      clearInterval(checkInterval);
      reject(new Error('Vite startup timeout'));
    }, 30000);
  });
}

/**
 * 启动electron项目
 * @returns 启动成功时 resolve，进程出错或超时则 reject
 */
async function createWindow() {
  try {
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
        preload: path.join(__dirname, 'preload.js')
      }
    });

    // 使用动态获取的 Vite 端口
    mainWindow.loadURL(`http://localhost:${vitePort}`);
    mainWindow.webContents.openDevTools();

    mainWindow.on('closed', () => {
      mainWindow = null;
    });
  } catch (err) {
    console.error(`[Main] Failed to start application: ${(err as Error).message}`);
    dialog.showErrorBox('启动失败', `无法启动后端服务：${(err as Error).message}\n\n请检查Python环境是否正确安装。`);
    app.quit();
  }
}

/**
 * 优雅关闭 Python 后端进程
 * 先发送 SIGTERM，3 秒内未退出则强杀，最后清理状态
 */
async function shutdownAll() {
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

//以下为Electron的主入口程序（调用层）
//应用启动就绪后创建窗口
app.whenReady().then(createWindow);

//注册一个处理器，在所有窗口都关闭时触发，关闭后端进程
app.on('window-all-closed', async () => {
  await shutdownAll();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

//注册一个处理器，在应用即将退出时触发，关闭后端进程
app.on('before-quit', async (event) => {
  if (pythonProcess && pythonProcess.exitCode === null) {
    event.preventDefault();
    await shutdownAll();
    app.quit();
  }
});

//注册一个处理器，当用户点击 macOS Dock 图标或应用被重新激活时触发。
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

//注册一个 IPC 接口，当渲染进程（前端）调用 ipcRenderer.invoke('get-backend-config') 时才执行，返回后端配置
ipcMain.handle('get-backend-config', () => {
  console.log(`[Main] get-backend-config called: port=${backendPort}, token=${backendToken}, ready=${isBackendReady}`);
  return { port: backendPort, token: backendToken, ready: isBackendReady };
});

//注册一个 IPC 接口，前端请求选择文件夹时才弹出系统对话
ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow!, {
    properties: ['openDirectory']
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});

//注册一个 IPC 接口，前端请求读取文件时才执行，返回文件内容
ipcMain.handle('read-file', async (_event, filePath: string) => {
  try {
    if (!fs.existsSync(filePath)) {
      return { success: false, error: '文件不存在' };
    }
    const stat = fs.statSync(filePath);
    if (stat.size > 5 * 1024 * 1024) {
      //限制文件最大为 5 MB
      return { success: false, error: '文件过大（超过5MB）' };
    }
    const content = fs.readFileSync(filePath, 'utf-8');//执行读取文件内容操作，这是node.js的模块，可以操作文件系统
    return { success: true, content, size: stat.size };
  } catch (err) {
    return { success: false, error: (err as Error).message };
  }
});
