import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { api, liveWsUrl } from "./api";
import type { AppConfig, AppLog, BotStatus, LiveMessage, PnlSummary, Trade } from "./types";

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 3 });

function emptyStatus(): BotStatus {
  return {
    running: false,
    mode: "paper",
    exchange: "binance",
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

function App() {
  const [status, setStatus] = useState<BotStatus>(emptyStatus());
  const [trades, setTrades] = useState<Trade[]>([]);
  const [pnl, setPnl] = useState<PnlSummary>({
    total_pnl: 0,
    daily_pnl: 0,
    net_pnl: 0,
    gross_pnl: 0,
    fees: 0,
    winrate: 0,
    profit_factor: 0,
    trade_count: 0,
    equity_curve: []
  });
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [logs, setLogs] = useState<AppLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ symbol: "", start: "", end: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadInitial();
    const ws = new WebSocket(liveWsUrl());
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data) as LiveMessage;
      if (message.status) setStatus(message.status);
      if (message.pnl) setPnl(normalizePnl(message.pnl));
      if (message.config) setConfig(message.config);
      if (message.trades) setTrades(message.trades);
      if (message.trade) setTrades((current) => [message.trade as Trade, ...current].slice(0, 500));
      if (message.message) setError(message.message);
    };
    ws.onerror = () => setError("WebSocket connection failed");
    return () => ws.close();
  }, []);

  const spreadSeries = useMemo(
    () => [
      { name: "Spread", value: status.spread },
      { name: "Edge", value: status.edge },
      { name: "Volatility", value: status.volatility },
      { name: "Imbalance", value: status.imbalance }
    ],
    [status]
  );

  async function loadInitial() {
    try {
      const [nextStatus, nextTrades, nextPnl, nextConfig, nextLogs] = await Promise.all([
        api.status(),
        api.trades(),
        api.pnl(),
        api.config(),
        api.logs()
      ]);
      setStatus(nextStatus);
      setTrades(nextTrades);
      setPnl(normalizePnl(nextPnl));
      setConfig(nextConfig);
      setLogs(nextLogs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function applyFilters() {
    const params = new URLSearchParams();
    if (filters.symbol) params.set("symbol", filters.symbol);
    if (filters.start) params.set("start", filters.start);
    if (filters.end) params.set("end", filters.end);
    const result = await api.trades(params.toString() ? `?${params.toString()}` : "");
    setTrades(result);
  }

  async function saveConfig() {
    if (!config) return;
    setSaving(true);
    try {
      const saved = await api.saveConfig(config);
      setConfig(saved);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function startStop(running: boolean) {
    try {
      setStatus(running ? await api.stop() : await api.start());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (!config) {
    return <main className="loading">Loading Spread System v3...</main>;
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Spread System v3</p>
          <h1>Trading Terminal</h1>
          <p className="muted">
            {status.exchange.toUpperCase()} · {status.symbol} · {status.mode.toUpperCase()} mode
          </p>
        </div>
        <div className="hero-actions">
          <span className={status.running ? "badge running" : "badge stopped"}>
            {status.running ? "RUNNING" : "STOPPED"}
          </span>
          <button onClick={() => startStop(status.running)}>
            {status.running ? "Stop Bot" : "Start Bot"}
          </button>
        </div>
      </header>

      {error && <section className="alert">{error}</section>}

      <section className="grid metrics-grid">
        <Metric title="Live PnL" value={currency.format(pnl.total_pnl)} large />
        <Metric title="Daily PnL" value={currency.format(pnl.daily_pnl)} />
        <Metric title="Winrate" value={percent.format(pnl.winrate)} />
        <Metric title="Profit Factor" value={pnl.profit_factor.toFixed(2)} />
        <Metric title="Spread" value={percent.format(status.spread)} />
        <Metric title="Volatility" value={percent.format(status.volatility)} />
      </section>

      <section className="grid two-column">
        <Panel title="Equity Curve">
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={pnl.equity_curve}>
              <defs>
                <linearGradient id="equity" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#3ddc97" stopOpacity={0.45} />
                  <stop offset="95%" stopColor="#3ddc97" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#233044" />
              <XAxis dataKey="timestamp" hide />
              <YAxis stroke="#8091a7" />
              <Tooltip />
              <Area dataKey="equity" stroke="#3ddc97" fill="url(#equity)" />
            </AreaChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Live Spread View">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={spreadSeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="#233044" />
              <XAxis dataKey="name" stroke="#8091a7" />
              <YAxis stroke="#8091a7" />
              <Tooltip formatter={(value) => percent.format(Number(value))} />
              <Line type="monotone" dataKey="value" stroke="#77a6ff" strokeWidth={3} />
            </LineChart>
          </ResponsiveContainer>
          <p className="muted">
            Risk/strategy block: {status.blocked_reason ?? "none"} · Last update:{" "}
            {status.last_update ?? "waiting"}
          </p>
        </Panel>
      </section>

      <section className="grid two-column align-start">
        <Panel title="Config Panel">
          <ConfigForm config={config} setConfig={setConfig} />
          <div className="button-row">
            <button onClick={saveConfig} disabled={saving}>
              SAVE CONFIG
            </button>
            <button onClick={saveConfig} disabled={saving}>
              APPLY CONFIG
            </button>
          </div>
        </Panel>

        <Panel title="Logs Viewer">
          <div className="logs">
            {logs.map((log) => (
              <div className="log-line" key={`${log.timestamp}-${log.message}`}>
                <span>{log.timestamp}</span>
                <strong>{log.level}</strong>
                <p>{log.message}</p>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <Panel title="Trade History">
        <div className="filters">
          <input
            placeholder="Symbol, e.g. BTC/USDT"
            value={filters.symbol}
            onChange={(event) => setFilters({ ...filters, symbol: event.target.value })}
          />
          <input
            type="date"
            value={filters.start}
            onChange={(event) => setFilters({ ...filters, start: event.target.value })}
          />
          <input
            type="date"
            value={filters.end}
            onChange={(event) => setFilters({ ...filters, end: event.target.value })}
          />
          <button onClick={applyFilters}>Apply Filters</button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Price</th>
                <th>Size</th>
                <th>PnL</th>
                <th>Fee</th>
                <th>Exchange</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.id}>
                  <td>{new Date(trade.timestamp).toLocaleString()}</td>
                  <td>{trade.symbol}</td>
                  <td className={trade.side}>{trade.side}</td>
                  <td>{trade.price.toFixed(4)}</td>
                  <td>{trade.size}</td>
                  <td className={trade.pnl >= 0 ? "positive" : "negative"}>{trade.pnl.toFixed(4)}</td>
                  <td>{trade.fee.toFixed(4)}</td>
                  <td>{trade.exchange}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </main>
  );
}

function normalizePnl(summary: PnlSummary): PnlSummary {
  const total = summary.total_pnl ?? summary.net_pnl ?? 0;
  return {
    ...summary,
    total_pnl: total,
    daily_pnl: summary.daily_pnl ?? total,
    net_pnl: summary.net_pnl ?? total,
    gross_pnl: summary.gross_pnl ?? total,
    fees: summary.fees ?? 0
  };
}

function Metric({ title, value, large = false }: { title: string; value: string; large?: boolean }) {
  return (
    <section className={large ? "metric large" : "metric"}>
      <span>{title}</span>
      <strong>{value}</strong>
    </section>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function ConfigForm({
  config,
  setConfig
}: {
  config: AppConfig;
  setConfig: (config: AppConfig) => void;
}) {
  return (
    <div className="config-grid">
      <label>
        Exchange
        <select
          value={config.exchange.name}
          onChange={(event) =>
            setConfig({ ...config, exchange: { ...config.exchange, name: event.target.value as AppConfig["exchange"]["name"] } })
          }
        >
          <option value="binance">Binance</option>
          <option value="bybit">Bybit</option>
          <option value="mexc">MEXC</option>
        </select>
      </label>
      <label>
        API Key
        <input
          value={config.exchange.api_key}
          onChange={(event) => setConfig({ ...config, exchange: { ...config.exchange, api_key: event.target.value } })}
        />
      </label>
      <label>
        API Secret
        <input
          type="password"
          value={config.exchange.api_secret}
          onChange={(event) => setConfig({ ...config, exchange: { ...config.exchange, api_secret: event.target.value } })}
        />
      </label>
      <label>
        API Password
        <input
          type="password"
          value={config.exchange.password}
          onChange={(event) => setConfig({ ...config, exchange: { ...config.exchange, password: event.target.value } })}
        />
      </label>
      <label>
        Trading Mode
        <select
          value={config.trading.mode}
          onChange={(event) =>
            setConfig({ ...config, trading: { ...config.trading, mode: event.target.value as AppConfig["trading"]["mode"] } })
          }
        >
          <option value="paper">Paper</option>
          <option value="live">Live</option>
        </select>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={config.trading.live_trading_enabled}
          onChange={(event) => setConfig({ ...config, trading: { ...config.trading, live_trading_enabled: event.target.checked } })}
        />
        Enable live trading
      </label>
      <label>
        Symbol
        <input
          value={config.trading.symbol}
          onChange={(event) => setConfig({ ...config, trading: { ...config.trading, symbol: event.target.value } })}
        />
      </label>
      <NumberField label="Maker Fee" value={config.fees.maker} onChange={(value) => setConfig({ ...config, fees: { ...config.fees, maker: value } })} />
      <NumberField label="Taker Fee" value={config.fees.taker} onChange={(value) => setConfig({ ...config, fees: { ...config.fees, taker: value } })} />
      <NumberField label="Min Edge" value={config.strategy.min_edge} onChange={(value) => setConfig({ ...config, strategy: { ...config.strategy, min_edge: value } })} />
      <NumberField label="Volatility Threshold" value={config.strategy.volatility_threshold} onChange={(value) => setConfig({ ...config, strategy: { ...config.strategy, volatility_threshold: value } })} />
      <NumberField label="Max Imbalance" value={config.strategy.imbalance_limit} onChange={(value) => setConfig({ ...config, strategy: { ...config.strategy, imbalance_limit: value } })} />
      <NumberField label="Min Liquidity" value={config.strategy.min_liquidity} onChange={(value) => setConfig({ ...config, strategy: { ...config.strategy, min_liquidity: value } })} />
      <NumberField label="Order Size" value={config.trading.order_size} onChange={(value) => setConfig({ ...config, trading: { ...config.trading, order_size: value } })} />
      <NumberField label="Max Daily Loss" value={config.risk.max_daily_loss} onChange={(value) => setConfig({ ...config, risk: { ...config.risk, max_daily_loss: value } })} />
      <NumberField label="Max Inventory Exposure" value={config.risk.max_inventory_exposure} onChange={(value) => setConfig({ ...config, risk: { ...config.risk, max_inventory_exposure: value } })} />
      <NumberField label="Max Position Size" value={config.risk.max_position_size} onChange={(value) => setConfig({ ...config, risk: { ...config.risk, max_position_size: value } })} />
      <NumberField label="Cooldown After Loss (s)" value={config.risk.cooldown_after_loss_seconds} onChange={(value) => setConfig({ ...config, risk: { ...config.risk, cooldown_after_loss_seconds: Math.round(value) } })} />
      <NumberField label="Cycle Interval (s)" value={config.trading.cycle_interval_seconds} onChange={(value) => setConfig({ ...config, trading: { ...config.trading, cycle_interval_seconds: value } })} />
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label>
      {label}
      <input type="number" step="any" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

export default App;
