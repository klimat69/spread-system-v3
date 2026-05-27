import type { AppConfig, AppLog, BotStatus, PnlSummary, Trade } from "./types";

declare global {
  interface Window {
    SPREAD_API_BASE?: string;
    SPREAD_WS_BASE?: string;
  }
}

const API_BASE = window.SPREAD_API_BASE ?? import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  status: () => request<BotStatus>("/status"),
  trades: (params = "") => request<Trade[]>(`/trades${params}`),
  pnl: () => request<PnlSummary>("/pnl"),
  config: () => request<AppConfig>("/config"),
  saveConfig: (config: AppConfig) =>
    request<AppConfig>("/config", { method: "POST", body: JSON.stringify(config) }),
  start: () => request<BotStatus>("/start", { method: "POST" }),
  stop: () => request<BotStatus>("/stop", { method: "POST" }),
  logs: () => request<AppLog[]>("/logs")
};

export function liveWsUrl(): string {
  const base = window.SPREAD_WS_BASE ?? import.meta.env.VITE_WS_BASE;
  if (base) return `${base}/ws/live`;
  const protocol = API_BASE.startsWith("https") ? "wss" : "ws";
  const host = API_BASE.replace(/^https?:\/\//, "");
  return `${protocol}://${host}/ws/live`;
}
