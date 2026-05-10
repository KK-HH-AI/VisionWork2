import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  //暴露的第一个API
  getBackendConfig: () => ipcRenderer.invoke('get-backend-config'),
  //暴露的第二个API
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  //暴露的第三个API
  readFile: (filePath: string) => ipcRenderer.invoke('read-file', filePath),
  //暴露的四个API
  onBackendExited: (callback: (data: { code: number | null }) => void) => {
    ipcRenderer.on('backend-exited', (_event, data) => callback(data));
  }
});
