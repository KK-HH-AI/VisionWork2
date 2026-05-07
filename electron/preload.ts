import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendConfig: () => ipcRenderer.invoke('get-backend-config'),
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  readFile: (filePath: string) => ipcRenderer.invoke('read-file', filePath),
  onBackendExited: (callback: (data: { code: number | null }) => void) => {
    ipcRenderer.on('backend-exited', (_event, data) => callback(data));
  }
});
