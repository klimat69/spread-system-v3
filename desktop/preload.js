const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("spreadConfig", {
  apiBase: "http://127.0.0.1:8000",
  wsBase: "ws://127.0.0.1:8000"
});
contextBridge.exposeInMainWorld("spreadSystemDesktop", {
  openBackendLog: () => ipcRenderer.invoke("open-backend-log"),
  getExchangeCredentials: (exchange) => ipcRenderer.invoke("keychain-get-credentials", { exchange }),
  setExchangeCredentials: (exchange, payload) =>
    ipcRenderer.invoke("keychain-set-credentials", {
      exchange,
      apiKey: payload.apiKey,
      apiSecret: payload.apiSecret,
      password: payload.password ?? ""
    }),
  clearExchangeCredentials: (exchange) => ipcRenderer.invoke("keychain-clear-credentials", { exchange }),
  onUpdaterStatus: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("updater-status", listener);
    return () => ipcRenderer.removeListener("updater-status", listener);
  },
  checkForUpdates: () => ipcRenderer.invoke("updater-check-now"),
  installUpdateNow: () => ipcRenderer.invoke("updater-install-now")
});
