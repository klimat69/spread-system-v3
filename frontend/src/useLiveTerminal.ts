import { useEffect, useState } from "react";
import { api, liveWsUrl } from "./api";
import type { BotStatus, DomDelta, DryRunOrder, LiveMessage, MarketState, SymbolListResponse, TapeTrade } from "./types";

function emptyStatus(): BotStatus {
  return {
    running: false,
    mode: "paper",
    exchange: "mexc",
    symbol: "BTC/USDT",
    last_error: null,
    last_update: null,
    spread: 0,
    edge: 0,
    volatility: 0,
    imbalance: 0,
    blocked_reason: null
  };
}

export function useLiveTerminal() {
  const [status, setStatus] = useState<BotStatus>(emptyStatus());
  const [market, setMarket] = useState<MarketState | null>(null);
  const [dryRunOrders, setDryRunOrders] = useState<DryRunOrder[]>([]);
  const [symbolCatalog, setSymbolCatalog] = useState<SymbolListResponse | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsHealth, setWsHealth] = useState("CONNECTING");
  const [wsReason, setWsReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [domDelta, setDomDelta] = useState<DomDelta | null>(null);
  const [lastTapeTrade, setLastTapeTrade] = useState<TapeTrade | null>(null);
  const [tickToRenderMs, setTickToRenderMs] = useState<number>(0);

  useEffect(() => {
    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;

    const connect = () => {
      socket = new WebSocket(liveWsUrl());
      socket.onopen = () => {
        setWsConnected(true);
        setError(null);
      };
      socket.onerror = () => setError("WebSocket connection failed");
      socket.onclose = () => {
        setWsConnected(false);
        reconnectTimer = window.setTimeout(connect, 1000);
      };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as LiveMessage;
          if (message.status) setStatus(message.status);
          if (message.type === "market" && message.state) {
            setMarket(message.state);
            setWsHealth(message.state.ws_status);
            setWsReason(message.state.ws_reason || "");
            if (message.dom_delta) setDomDelta(message.dom_delta);
            if (message.tape_trade) setLastTapeTrade(message.tape_trade);
            const tsExchange = message.dom_delta?.ts_exchange ?? message.tape_trade?.ts_exchange;
            if (typeof tsExchange === "number" && Number.isFinite(tsExchange)) {
                setTickToRenderMs(Math.max(0, Date.now() - tsExchange));
            } else {
                setTickToRenderMs(0);
            }
          }
          if (message.type === "snapshot") {
            if (message.market) {
              setMarket(message.market);
              setWsHealth(message.market.ws_status);
              setWsReason(message.market.ws_reason || "");
            } else {
              const snapshotHealth = message.market_data as { status?: string; reason?: string } | undefined;
              if (snapshotHealth?.status) setWsHealth(String(snapshotHealth.status));
              if (snapshotHealth?.reason) setWsReason(String(snapshotHealth.reason));
            }
            if (Array.isArray(message.dry_run_orders)) setDryRunOrders(message.dry_run_orders);
          }
          if (message.type === "dry_run" && Array.isArray(message.orders as DryRunOrder[] | undefined)) {
            setDryRunOrders((message.orders as DryRunOrder[]).slice(-100));
          }
          if (message.message) setError(message.message);
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
        }
      };
    };

    connect();
    void api.marketState()
      .then((state) => {
        setMarket(state);
        setWsHealth(state.ws_status);
        setWsReason(state.ws_reason || "");
      })
      .catch(() => {
        // Ignore boot race, WS reconnect handles it.
      });

    return () => {
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  return {
    status,
    market,
    dryRunOrders,
    symbolCatalog,
    setSymbolCatalog,
    wsConnected,
    wsHealth,
    wsReason,
    error,
    setError,
    domDelta,
    lastTapeTrade,
    tickToRenderMs
  };
}
