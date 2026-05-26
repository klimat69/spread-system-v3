const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("spreadConfig", {
  apiBase: "http://127.0.0.1:8000",
  wsBase: "ws://127.0.0.1:8000"
});
contextBridge.exposeInMainWorld("spreadSystemDesktop", {
  openBackendLog: () => ipcRenderer.invoke("open-backend-log")
});
