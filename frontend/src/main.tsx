import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

declare global {
  interface Window {
    spreadConfig?: {
      apiBase?: string;
      wsBase?: string;
    };
    SPREAD_API_BASE?: string;
    SPREAD_WS_BASE?: string;
  }
}

if (window.spreadConfig?.apiBase && !window.SPREAD_API_BASE) {
  window.SPREAD_API_BASE = window.spreadConfig.apiBase;
}
if (window.spreadConfig?.wsBase && !window.SPREAD_WS_BASE) {
  window.SPREAD_WS_BASE = window.spreadConfig.wsBase;
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
