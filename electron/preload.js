const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendConfig: () => ipcRenderer.invoke('get-backend-config'),
  selectFolder: () => ipcRenderer.invoke('select-folder')
});
