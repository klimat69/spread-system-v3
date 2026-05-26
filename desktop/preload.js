const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("SPREAD_API_BASE", "http://127.0.0.1:8000");
contextBridge.exposeInMainWorld("SPREAD_WS_BASE", "ws://127.0.0.1:8000");
contextBridge.exposeInMainWorld("spreadSystemDesktop", {
  openBackendLog: () => ipcRenderer.invoke("open-backend-log")
});
