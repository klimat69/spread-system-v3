import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "./api";
import { useLiveTerminal } from "./useLiveTerminal";
import type { AppConfig, MarketType } from "./types";

const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 3 });

function quoteFromSymbol(symbol: string): string {
  const pair = symbol.split(":")[0];
  return (pair.split("/")[1] ?? "USDT").toUpperCase();
}

function normalizeMexcConfig(config: AppConfig): AppConfig {
  return {
    ...config,
    exchange: { ...config.exchange, name: "mexc", sandbox: false },
    trading: {
      ...config.trading,
      market_type: config.trading.market_type ?? "swap",
      auto_trade_enabled: config.trading.auto_trade_enabled ?? false
    }
  };
}

function mexcFuturesUrl(symbol: string): string {
  const market = symbol.split(":")[0].replace("/", "_").toUpperCase();
  return `https://www.mexc.com/ru-RU/futures/${market}`;
}

function tradingViewSymbol(symbol: string, marketType: MarketType): string {
  const normalized = symbol.split(":")[0].replace("/", "").toUpperCase();
  return marketType === "swap" ? `MEXC:${normalized}.P` : `MEXC:${normalized}`;
}

function tradingViewEmbedUrl(symbol: string, marketType: MarketType): string {
  const tvSymbol = encodeURIComponent(tradingViewSymbol(symbol, marketType));
  return `https://s.tradingview.com/widgetembed/?frameElementId=tv_mexc_realtime&symbol=${tvSymbol}&interval=1&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=f1f3f6&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=0&studies=[]&hideideas=1`;
}

export default function App() {
  const { status, market, dryRunOrders, wsConnected, wsHealth, error, symbolCatalog, setSymbolCatalog, setError } = useLiveTerminal();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [quoteCurrency, setQuoteCurrency] = useState("USDT");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [midSeries, setMidSeries] = useState<Array<{ t: string; mid: number }>>([]);

  const quotes = symbolCatalog?.quotes ?? [];
  const symbols = symbolCatalog?.symbols_by_quote?.[quoteCurrency] ?? symbolCatalog?.symbols ?? [];
  const filteredSymbols = symbols.filter((symbol) => symbol.toLowerCase().includes(symbolSearch.trim().toLowerCase()));

  useEffect(() => {
    void (async () => {
      try {
        const cfg = normalizeMexcConfig(await api.config());
        setConfig(cfg);
        const quote = quoteFromSymbol(cfg.trading.symbol);
        const catalog = await api.symbols(cfg.trading.market_type, quote);
        setSymbolCatalog(catalog);
        setQuoteCurrency(catalog.quote ?? quote);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
  }, []);

  useEffect(() => {
    if (!market || market.best_bid <= 0 || market.best_ask <= 0) return;
    const mid = (market.best_bid + market.best_ask) / 2;
    const t = new Date().toLocaleTimeString();
    setMidSeries((prev) => [...prev.slice(-299), { t, mid }]);
  }, [market?.best_bid, market?.best_ask]);

  const futuresSeries =
    market?.candles_1m?.map((candle) => ({
      t: new Date(candle.ts).toLocaleTimeString(),
      px: candle.close
    })) ?? [];

  async function loadSymbols(marketType: MarketType, quote?: string) {
    const catalog = await api.symbols(marketType, quote);
    setSymbolCatalog(catalog);
    if (catalog.quote) setQuoteCurrency(catalog.quote);
    return catalog;
  }

  async function saveConfig() {
    if (!config) return;
    setSaving(true);
    try {
      const saved = await api.saveConfig(normalizeMexcConfig(config));
      setConfig(normalizeMexcConfig(saved));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function toggleStart() {
    try {
      await (status.running ? api.stop() : api.start());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (!config) return <main className="loading">Loading MEXC terminal...</main>;

  return (
    <main className="terminal-shell">
      <header className="terminal-top">
        <div className="top-left">
          <strong>Spread System v3 · MEXC Terminal</strong>
          <span className={wsConnected ? "ok" : "bad"}>{wsConnected ? "WS Connected" : "WS Disconnected"}</span>
          <span className={wsHealth === "OK" ? "ok" : "bad"}>Feed: {wsHealth}</span>
        </div>
        <div className="top-right">
          <label className="switch">
            Auto Trade
            <input
              type="checkbox"
              checked={config.trading.auto_trade_enabled}
              onChange={(event) =>
                setConfig({ ...config, trading: { ...config.trading, auto_trade_enabled: event.target.checked } })
              }
            />
          </label>
          <button className="primary" onClick={toggleStart}>
            {status.running ? "Stop" : "Start"}
          </button>
        </div>
      </header>
      {error && <div className="alert">{error}</div>}

      <section className="terminal-grid">
        <aside className="left-panel panel">
          <h3>Markets</h3>
          <label>
            Market
            <select
              value={config.trading.market_type}
              onChange={async (event) => {
                const marketType = event.target.value as MarketType;
                const catalog = await loadSymbols(marketType);
                setConfig({ ...config, trading: { ...config.trading, market_type: marketType, symbol: catalog.symbols[0] ?? config.trading.symbol } });
              }}
            >
              <option value="spot">Spot</option>
              <option value="swap">Futures (perpetual)</option>
            </select>
          </label>
          {config.trading.market_type === "spot" && quotes.length > 0 && (
            <div className="quote-tabs">
              {quotes.map((quote) => (
                <button
                  key={quote}
                  className={quote === quoteCurrency ? "active" : ""}
                  onClick={async () => {
                    const catalog = await loadSymbols("spot", quote);
                    setConfig({ ...config, trading: { ...config.trading, symbol: catalog.symbols[0] ?? config.trading.symbol } });
                  }}
                >
                  {quote}
                </button>
              ))}
            </div>
          )}
          <input placeholder="Search pair" value={symbolSearch} onChange={(e) => setSymbolSearch(e.target.value)} />
          <div className="pair-list">
            {(filteredSymbols.length > 0 ? filteredSymbols : [config.trading.symbol]).slice(0, 200).map((symbol) => (
              <button
                key={symbol}
                className={symbol === config.trading.symbol ? "active" : ""}
                onClick={() => setConfig({ ...config, trading: { ...config.trading, symbol } })}
              >
                {symbol}
              </button>
            ))}
          </div>
        </aside>

        <section className="center-panel panel">
          <h3>Realtime Metrics</h3>
          <div className="mid-chart">
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={config.trading.market_type === "swap" ? futuresSeries : midSeries}>
                <XAxis dataKey="t" hide />
                <YAxis domain={["auto", "auto"]} width={60} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value) => Number(value).toFixed(4)} />
                <Line
                  type="monotone"
                  dataKey={config.trading.market_type === "swap" ? "px" : "mid"}
                  stroke="#60a5fa"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="broadcast-header">
            <strong>Live Broadcast</strong>
            <a href={mexcFuturesUrl(config.trading.symbol)} target="_blank" rel="noreferrer">
              Open on MEXC
            </a>
          </div>
          <div className="broadcast-frame-wrap">
            <iframe
              key={`${config.trading.market_type}-${config.trading.symbol}`}
              title="MEXC Live Broadcast"
              src={tradingViewEmbedUrl(config.trading.symbol, config.trading.market_type)}
              className="broadcast-frame"
              loading="lazy"
            />
          </div>
          <div className="metrics">
            <div><span>Best Bid</span><strong>{market ? market.best_bid.toFixed(4) : "0.0000"}</strong></div>
            <div><span>Best Ask</span><strong>{market ? market.best_ask.toFixed(4) : "0.0000"}</strong></div>
            <div><span>Spread</span><strong>{percent.format(market?.spread ?? 0)}</strong></div>
            <div><span>Imbalance</span><strong>{percent.format(market?.imbalance ?? 0)}</strong></div>
          </div>
          <div className="status-row">
            <span>Mode: {config.trading.mode.toUpperCase()}</span>
            <span>Auto: {config.trading.auto_trade_enabled ? "ON" : "OFF"}</span>
            <span>Blocked: {status.blocked_reason ?? "none"}</span>
          </div>
          <div className="settings">
            <label>
              API Key
              <input value={config.exchange.api_key} onChange={(e) => setConfig({ ...config, exchange: { ...config.exchange, api_key: e.target.value } })} />
            </label>
            <label>
              API Secret
              <input type="password" value={config.exchange.api_secret} onChange={(e) => setConfig({ ...config, exchange: { ...config.exchange, api_secret: e.target.value } })} />
            </label>
            <label>
              API Password
              <input type="password" value={config.exchange.password} onChange={(e) => setConfig({ ...config, exchange: { ...config.exchange, password: e.target.value } })} />
            </label>
            <label>
              Mode
              <select value={config.trading.mode} onChange={(e) => setConfig({ ...config, trading: { ...config.trading, mode: e.target.value as "paper" | "live" } })}>
                <option value="paper">Paper</option>
                <option value="live">Live</option>
              </select>
            </label>
            <label className="switch">
              Enable live orders
              <input
                type="checkbox"
                checked={config.trading.live_trading_enabled}
                onChange={(e) => setConfig({ ...config, trading: { ...config.trading, live_trading_enabled: e.target.checked } })}
              />
            </label>
            <label>
              Order size
              <input
                type="number"
                step="any"
                value={config.trading.order_size}
                onChange={(e) => setConfig({ ...config, trading: { ...config.trading, order_size: Number(e.target.value) || config.trading.order_size } })}
              />
            </label>
            <button className="primary" onClick={saveConfig} disabled={saving}>{saving ? "Saving..." : "Save Config"}</button>
          </div>
          <div className="dry-run">
            <h4>Paper Dry-Run Events</h4>
            {dryRunOrders.length === 0 && <p>No dry-run events yet.</p>}
            {dryRunOrders.slice(-12).reverse().map((order) => (
              <div key={order.id} className="dry-item">
                <span>{order.timestamp}</span>
                <strong>{order.side.toUpperCase()} {order.size}</strong>
                <span>@ {order.price.toFixed(4)} · {order.status}</span>
              </div>
            ))}
          </div>
        </section>

        <aside className="right-panel panel">
          <h3>Order Book</h3>
          <div className="book">
            <div className="book-side">
              <h4>Asks</h4>
              {(market?.asks ?? []).slice(0, 10).map((level) => (
                <div key={`a-${level.price}-${level.size}`} className="level sell">
                  <span>{level.price.toFixed(4)}</span>
                  <span>{level.size.toFixed(4)}</span>
                </div>
              ))}
            </div>
            <div className="book-side">
              <h4>Bids</h4>
              {(market?.bids ?? []).slice(0, 10).map((level) => (
                <div key={`b-${level.price}-${level.size}`} className="level buy">
                  <span>{level.price.toFixed(4)}</span>
                  <span>{level.size.toFixed(4)}</span>
                </div>
              ))}
            </div>
          </div>
          <h3>Live Trades</h3>
          <div className="tape">
            {(market?.recent_trades ?? []).slice(-60).reverse().map((trade) => (
              <div key={`${trade.timestamp}-${trade.price}-${trade.size}`} className={`tape-item ${trade.side}`}>
                <span>{new Date(trade.timestamp).toLocaleTimeString()}</span>
                <strong>{trade.price.toFixed(4)}</strong>
                <span>{trade.size.toFixed(4)}</span>
              </div>
            ))}
          </div>
          <div className="mini-pnl">
            Spread: {percent.format(market?.spread ?? 0)} · Imbalance: {percent.format(market?.imbalance ?? 0)}
          </div>
        </aside>
      </section>
    </main>
  );
}
