import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  Bot,
  History,
  LineChart as LineChartIcon,
  Save,
  Settings,
  Square,
  TrendingUp
} from "lucide-react";
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
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const WS_URL =
  import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/live`;

const formatMoney = (value) =>
  Number(value || 0).toLocaleString(undefined, { style: "currency", currency: "USD" });
const formatPct = (value) => `${(Number(value || 0) * 100).toFixed(3)}%`;

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function App() {
  const [status, setStatus] = useState({ running: false });
  const [pnl, setPnl] = useState({ net_pnl: 0, equity_curve: [], winrate: 0, profit_factor: 0 });
  const [trades, setTrades] = useState([]);
  const [logs, setLogs] = useState([]);
  const [config, setConfig] = useState(null);
  const [tick, setTick] = useState(null);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ symbol: "", start: "", end: "" });

  const refresh = async () => {
    const [nextStatus, nextPnl, nextTrades, nextConfig, nextLogs] = await Promise.all([
      api("/status"),
      api("/pnl"),
      api("/trades"),
      api("/config"),
      api("/logs")
    ]);
    setStatus(nextStatus);
    setPnl(nextPnl);
    setTrades(nextTrades);
    setConfig(nextConfig);
    setLogs(nextLogs);
  };

  useEffect(() => {
    refresh().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.status) setStatus(message.status);
      if (message.pnl) setPnl(message.pnl);
      if (message.config) setConfig(message.config);
      if (message.trades) setTrades(message.trades);
      if (message.tick) setTick(message.tick);
      if (message.trade) setTrades((current) => [message.trade, ...current]);
      if (message.event) setLogs((current) => [message.event, ...current].slice(0, 200));
    };
    socket.onerror = () => setError("Live websocket disconnected or unavailable");
    return () => socket.close();
  }, []);

  const filteredTrades = useMemo(() => {
    return trades.filter((trade) => {
      if (filters.symbol && !trade.symbol.includes(filters.symbol.toUpperCase())) return false;
      if (filters.start && trade.timestamp < filters.start) return false;
      if (filters.end && trade.timestamp > filters.end) return false;
      return true;
    });
  }, [trades, filters]);

  const saveConfig = async () => {
    setError("");
    try {
      const saved = await api("/config", { method: "POST", body: JSON.stringify(config) });
      setConfig(saved);
    } catch (err) {
      setError(err.message);
    }
  };

  const startBot = async () => {
    setError("");
    try {
      setStatus(await api("/start", { method: "POST" }));
    } catch (err) {
      setError(err.message);
    }
  };

  const stopBot = async () => {
    setError("");
    try {
      setStatus(await api("/stop", { method: "POST" }));
    } catch (err) {
      setError(err.message);
    }
  };

  if (!config) {
    return <div className="loading">Loading Spread System v3...</div>;
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Production trading terminal</p>
          <h1>Spread System v3</h1>
          <p className="subtle">Fee-aware spread engine with SQLite history, hot config, and live WebSocket telemetry.</p>
        </div>
        <div className={`status-pill ${status.running ? "running" : "stopped"}`}>
          <Bot size={18} />
          {status.running ? "RUNNING" : "STOPPED"}
        </div>
      </header>

      {error && (
        <section className="alert">
          <AlertTriangle size={18} /> {error}
        </section>
      )}

      <section className="grid metrics">
        <Metric icon={<TrendingUp />} label="Live Net PnL" value={formatMoney(pnl.net_pnl)} highlight />
        <Metric icon={<Activity />} label="Spread" value={formatPct(tick?.spread)} />
        <Metric icon={<LineChartIcon />} label="Edge After Fees" value={formatPct(tick?.edge)} />
        <Metric icon={<AlertTriangle />} label="Volatility" value={formatPct(tick?.volatility)} />
      </section>

      <section className="grid two-col">
        <Panel title="Equity Curve">
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={pnl.equity_curve || []}>
              <defs>
                <linearGradient id="equity" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.6} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#22314f" />
              <XAxis dataKey="timestamp" hide />
              <YAxis stroke="#90a4c7" />
              <Tooltip contentStyle={{ background: "#101a2e", border: "1px solid #22314f" }} />
              <Area type="monotone" dataKey="equity" stroke="#22c55e" fill="url(#equity)" />
            </AreaChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Spread Live View">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={tick ? [{ name: "now", spread: tick.spread, edge: tick.edge, volatility: tick.volatility }] : []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#22314f" />
              <XAxis dataKey="name" stroke="#90a4c7" />
              <YAxis stroke="#90a4c7" />
              <Tooltip contentStyle={{ background: "#101a2e", border: "1px solid #22314f" }} />
              <Line type="monotone" dataKey="spread" stroke="#60a5fa" strokeWidth={3} />
              <Line type="monotone" dataKey="edge" stroke="#22c55e" strokeWidth={3} />
              <Line type="monotone" dataKey="volatility" stroke="#f59e0b" strokeWidth={3} />
            </LineChart>
          </ResponsiveContainer>
          <div className="tick-details">
            <span>Reason: {tick?.strategy_reason || "waiting"}</span>
            <span>Risk: {tick?.risk_reason || "waiting"}</span>
            <span>Liquidity: {Number(tick?.liquidity || 0).toFixed(2)}</span>
          </div>
        </Panel>
      </section>

      <section className="grid two-col">
        <Panel title="Bot Control">
          <div className="button-row">
            <button onClick={startBot} className="primary"><Activity size={16} /> Start Bot</button>
            <button onClick={stopBot}><Square size={16} /> Stop Bot</button>
          </div>
          <div className="stats-row">
            <span>Winrate: {formatPct(pnl.winrate)}</span>
            <span>Profit factor: {Number(pnl.profit_factor || 0).toFixed(2)}</span>
            <span>Trades: {pnl.trade_count || 0}</span>
          </div>
          <pre className="status-json">{JSON.stringify(status, null, 2)}</pre>
        </Panel>

        <Panel title="Logs Viewer">
          <div className="log-list">
            {logs.map((log) => (
              <div className={`log ${log.level}`} key={log.id || `${log.timestamp}-${log.message}`}>
                <span>{log.timestamp}</span>
                <strong>{log.level}</strong>
                <p>{log.message}</p>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <Panel title="Config Panel">
        <ConfigEditor config={config} setConfig={setConfig} />
        <div className="button-row">
          <button onClick={saveConfig} className="primary"><Save size={16} /> Save Config</button>
          <button onClick={saveConfig}><Settings size={16} /> Apply Config (Hot Reload)</button>
        </div>
      </Panel>

      <Panel title="History">
        <div className="filters">
          <label>Symbol <input value={filters.symbol} onChange={(e) => setFilters({ ...filters, symbol: e.target.value })} placeholder="BTC/USDT" /></label>
          <label>Start <input type="datetime-local" value={filters.start} onChange={(e) => setFilters({ ...filters, start: e.target.value })} /></label>
          <label>End <input type="datetime-local" value={filters.end} onChange={(e) => setFilters({ ...filters, end: e.target.value })} /></label>
        </div>
        <TradeTable trades={filteredTrades} />
      </Panel>
    </main>
  );
}

function Metric({ icon, label, value, highlight = false }) {
  return (
    <article className={`metric-card ${highlight ? "highlight" : ""}`}>
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function Panel({ title, children }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function ConfigEditor({ config, setConfig }) {
  const set = (path, value) => {
    setConfig((current) => {
      const next = structuredClone(current);
      let target = next;
      for (const part of path.slice(0, -1)) target = target[part];
      target[path[path.length - 1]] = value;
      return next;
    });
  };

  return (
    <div className="config-grid">
      <fieldset>
        <legend>Exchange</legend>
        <label>Exchange
          <select value={config.exchange.name} onChange={(e) => set(["exchange", "name"], e.target.value)}>
            <option value="binance">Binance</option>
            <option value="bybit">Bybit</option>
            <option value="mexc">MEXC</option>
          </select>
        </label>
        <label>API Key <input type="password" value={config.exchange.api_key} onChange={(e) => set(["exchange", "api_key"], e.target.value)} /></label>
        <label>API Secret <input type="password" value={config.exchange.api_secret} onChange={(e) => set(["exchange", "api_secret"], e.target.value)} /></label>
        <label>Password <input type="password" value={config.exchange.password} onChange={(e) => set(["exchange", "password"], e.target.value)} /></label>
        <label className="checkbox"><input type="checkbox" checked={config.exchange.sandbox} onChange={(e) => set(["exchange", "sandbox"], e.target.checked)} /> Sandbox</label>
      </fieldset>

      <fieldset>
        <legend>Trading</legend>
        <label>Mode
          <select value={config.trading.mode} onChange={(e) => set(["trading", "mode"], e.target.value)}>
            <option value="paper">Paper</option>
            <option value="live">Live</option>
          </select>
        </label>
        <label>Symbol <input value={config.trading.symbol} onChange={(e) => set(["trading", "symbol"], e.target.value)} /></label>
        <label>Order Size <NumberInput value={config.trading.order_size} onChange={(v) => set(["trading", "order_size"], v)} /></label>
        <label>Cycle Seconds <NumberInput value={config.trading.cycle_interval_seconds} onChange={(v) => set(["trading", "cycle_interval_seconds"], v)} /></label>
        <label className="checkbox"><input type="checkbox" checked={config.trading.live_trading_enabled} onChange={(e) => set(["trading", "live_trading_enabled"], e.target.checked)} /> Enable Live Orders</label>
      </fieldset>

      <fieldset>
        <legend>Fees And Strategy</legend>
        <label>Maker Fee <NumberInput value={config.fees.maker} onChange={(v) => set(["fees", "maker"], v)} /></label>
        <label>Taker Fee <NumberInput value={config.fees.taker} onChange={(v) => set(["fees", "taker"], v)} /></label>
        <label>Min Edge <NumberInput value={config.strategy.min_edge} onChange={(v) => set(["strategy", "min_edge"], v)} /></label>
        <label>Volatility Threshold <NumberInput value={config.strategy.volatility_threshold} onChange={(v) => set(["strategy", "volatility_threshold"], v)} /></label>
        <label>Imbalance Limit <NumberInput value={config.strategy.imbalance_limit} onChange={(v) => set(["strategy", "imbalance_limit"], v)} /></label>
        <label>Min Liquidity <NumberInput value={config.strategy.min_liquidity} onChange={(v) => set(["strategy", "min_liquidity"], v)} /></label>
      </fieldset>

      <fieldset>
        <legend>Risk Limits</legend>
        <label>Max Daily Loss <NumberInput value={config.risk.max_daily_loss} onChange={(v) => set(["risk", "max_daily_loss"], v)} /></label>
        <label>Max Inventory Exposure <NumberInput value={config.risk.max_inventory_exposure} onChange={(v) => set(["risk", "max_inventory_exposure"], v)} /></label>
        <label>Max Position Size <NumberInput value={config.risk.max_position_size} onChange={(v) => set(["risk", "max_position_size"], v)} /></label>
        <label>Cooldown After Loss Seconds <NumberInput value={config.risk.cooldown_after_loss_seconds} onChange={(v) => set(["risk", "cooldown_after_loss_seconds"], v)} /></label>
      </fieldset>
    </div>
  );
}

function NumberInput({ value, onChange }) {
  return <input type="number" step="any" value={value} onChange={(e) => onChange(Number(e.target.value))} />;
}

function TradeTable({ trades }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th><History size={14} /> Time</th>
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
            <tr key={trade.id || `${trade.timestamp}-${trade.side}`}>
              <td>{trade.timestamp}</td>
              <td>{trade.symbol}</td>
              <td className={trade.side}>{trade.side}</td>
              <td>{Number(trade.price).toFixed(4)}</td>
              <td>{Number(trade.size).toFixed(6)}</td>
              <td>{formatMoney(trade.pnl)}</td>
              <td>{formatMoney(trade.fee)}</td>
              <td>{trade.exchange}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
