import type {
  AppConfig,
  AppLog,
  BotFill,
  BotOrder,
  BotStatus,
  MarketStateEnvelope,
  PnlSummary,
  SymbolListResponse,
  Trade
} from "./types";

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
    const raw = await response.text();
    let detail = raw;
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown; message?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
      else if (typeof parsed.message === "string") detail = parsed.message;
      else if (parsed.detail) detail = JSON.stringify(parsed.detail);
    } catch {
      // keep raw text for non-json errors
    }
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  status: () => request<BotStatus>("/status"),
  trades: (params = "") => request<Trade[]>(`/trades${params}`),
  orders: (params = "") => request<BotOrder[]>(`/orders${params}`),
  fills: (params = "") => request<BotFill[]>(`/fills${params}`),
  pnl: () => request<PnlSummary>("/pnl"),
  config: () => request<AppConfig>("/config"),
  saveConfig: (config: AppConfig) =>
    request<AppConfig>("/config", { method: "POST", body: JSON.stringify(config) }),
  symbols: (marketType: "spot" | "swap", quote?: string) => {
    const params = new URLSearchParams({ market_type: marketType });
    if (quote) params.set("quote", quote);
    return request<SymbolListResponse>(`/symbols?${params.toString()}`);
  },
  marketState: () => request<MarketStateEnvelope>("/market/state"),
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
