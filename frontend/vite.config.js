import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/status": "http://127.0.0.1:8000",
      "/trades": "http://127.0.0.1:8000",
      "/pnl": "http://127.0.0.1:8000",
      "/config": "http://127.0.0.1:8000",
      "/start": "http://127.0.0.1:8000",
      "/stop": "http://127.0.0.1:8000",
      "/logs": "http://127.0.0.1:8000",
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true
      }
    }
  }
});
