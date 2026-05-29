import { useEffect, useMemo, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "./api";
import {
  type ChartInterval,
  displaySymbol,
  isGoldOrXaut,
  mexcPlatformUrl,
  orderedSymbolList,
  parseLocaleNumber,
  quoteFromSymbol,
  resolveGoldFuturesSymbol,
  symbolNote,
  tradingViewEmbedUrl
} from "./mexcDisplay";
import { blockedReasonRu, feedReasonRu, feedStatusRu, ru, type UpdaterStatusPayload } from "./ru";
import { useLiveTerminal } from "./useLiveTerminal";
import type { AppConfig, MarketType } from "./types";

const percent = new Intl.NumberFormat("ru-RU", { style: "percent", maximumFractionDigits: 3 });

function buildDemoGoldConfig(config: AppConfig, goldSymbol: string): AppConfig {
  return {
    ...config,
    trading: {
      ...config.trading,
      mode: "paper",
      market_type: "swap",
      symbol: goldSymbol,
      auto_trade_enabled: true,
      demo_relaxed_signals: true,
      live_trading_enabled: false
    },
    strategy: {
      ...config.strategy,
      imbalance_limit: 0.18,
      tape_aggression_entry_threshold: 0.1,
      momentum_burst_multiplier: 1.15,
      min_liquidity: 100,
      min_tape_notional: 40,
      max_holding_seconds: 5,
      market_data_stale_after_seconds: 3,
      max_orderbook_age_seconds: 2,
      tape_window_seconds: 2,
      entry_cooldown_seconds: 2
    },
    simple_scalp: {
      ...config.simple_scalp!,
      spread_min: 0.0001,
      imbalance_min: 0.12,
      aggression_min: 0.08
    }
  };
}

function normalizeMexcConfig(config: AppConfig): AppConfig {
  return {
    ...config,
    exchange: { ...config.exchange, name: "mexc", sandbox: false },
    trading: {
      ...config.trading,
      market_type: config.trading.market_type ?? "swap",
      auto_trade_enabled: config.trading.auto_trade_enabled ?? false,
      demo_relaxed_signals: config.trading.demo_relaxed_signals ?? false
    },
    simple_scalp: config.simple_scalp ?? {
      spread_min: 0.0002,
      imbalance_min: 0.2,
      aggression_min: 0.15,
      stale_order_after_seconds: 1.5,
      replace_move_bps: 3
    }
  };
}

export default function App() {
  const {
    status,
    market,
    dryRunOrders,
    wsConnected,
    wsHealth,
    wsReason,
    error,
    symbolCatalog,
    setSymbolCatalog,
    setError,
    tickToRenderMs
  } = useLiveTerminal();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [quoteCurrency, setQuoteCurrency] = useState("USDT");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [midSeries, setMidSeries] = useState<Array<{ t: string; mid: number }>>([]);
  const [updaterStatus, setUpdaterStatus] = useState<UpdaterStatusPayload | null>(null);
  const [chartInterval, setChartInterval] = useState<ChartInterval>("1S");

  const quotes = symbolCatalog?.quotes ?? [];
  const orderedSymbols = useMemo(
    () => orderedSymbolList(symbolCatalog, quoteCurrency, symbolSearch),
    [symbolCatalog, quoteCurrency, symbolSearch]
  );
  const popularSymbols = useMemo(() => {
    const popular = symbolCatalog?.popular_symbols ?? [];
    const q = symbolSearch.trim().toLowerCase();
    if (!q) return popular;
    return popular.filter((s) => s.toLowerCase().includes(q) || displaySymbol(s, symbolCatalog).toLowerCase().includes(q));
  }, [symbolCatalog, symbolSearch]);
  const restSymbols = orderedSymbols.filter((s) => !popularSymbols.includes(s)).slice(0, 200);

  const goldFuturesSymbol = useMemo(
    () => (symbolCatalog ? resolveGoldFuturesSymbol(symbolCatalog) : "XAUT/USDT:USDT"),
    [symbolCatalog]
  );
  const showGoldFuturesSection = config?.trading.market_type === "swap";

  const pairNote = config ? symbolNote(config.trading.symbol, symbolCatalog) : "";

  useEffect(() => {
    const desktop = window.spreadSystemDesktop;
    if (!desktop?.onUpdaterStatus) return;
    return desktop.onUpdaterStatus((payload) => {
      setUpdaterStatus(payload as UpdaterStatusPayload);
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      for (let attempt = 0; attempt < 45 && !cancelled; attempt += 1) {
        if (attempt > 0) await new Promise((resolve) => setTimeout(resolve, 2000));
        try {
          const cfg = normalizeMexcConfig(await api.config());
          if (cancelled) return;
          setConfig(cfg);
          const quote = quoteFromSymbol(cfg.trading.symbol);
          const catalog = await api.symbols(cfg.trading.market_type, quote);
          if (cancelled) return;
          setSymbolCatalog(catalog);
          setQuoteCurrency(catalog.quote ?? quote);
          setError(null);
          return;
        } catch (err) {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!market || market.best_bid <= 0 || market.best_ask <= 0) return;
    const mid = (market.best_bid + market.best_ask) / 2;
    const t = new Date().toLocaleTimeString("ru-RU");
    setMidSeries((prev) => [...prev.slice(-299), { t, mid }]);
  }, [market?.best_bid, market?.best_ask]);

  const futuresSeries =
    market?.candles_1m?.map((candle) => ({
      t: new Date(candle.ts).toLocaleTimeString("ru-RU"),
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

  function pickSymbol(symbol: string, marketType?: MarketType) {
    if (!config) return;
    const nextMarket = marketType ?? config.trading.market_type;
    setConfig({
      ...config,
      trading: { ...config.trading, market_type: nextMarket, symbol }
    });
    if (quoteFromSymbol(symbol) !== quoteCurrency) {
      setQuoteCurrency(quoteFromSymbol(symbol));
    }
  }

  function pickGoldFutures() {
    if (!config) return;
    setQuoteCurrency("USDT");
    pickSymbol(goldFuturesSymbol, "swap");
  }

  function applyDemoGoldPreset() {
    if (!config) return;
    setConfig(buildDemoGoldConfig(config, goldFuturesSymbol));
    setQuoteCurrency("USDT");
  }

  if (!config) {
    return (
      <main className="loading">
        {ru.loading}
        {error ? <p className="loading-hint">{error}</p> : null}
      </main>
    );
  }

  const activeDisplay = displaySymbol(config.trading.symbol, symbolCatalog);

  return (
    <main className="terminal-shell">
      <header className="terminal-top">
        <div className="top-left">
          <strong>{ru.title}</strong>
          <span className="pair-badge">{activeDisplay}</span>
          <span className={wsConnected ? "ok" : "bad"}>{wsConnected ? ru.wsConnected : ru.wsDisconnected}</span>
          <span
            className={wsHealth === "OK" ? "ok" : wsHealth === "RECOVERING" ? "warn" : "bad"}
            title={wsReason ? feedReasonRu(wsReason) : undefined}
          >
            {ru.feed}: {feedStatusRu(wsHealth)}
            {wsHealth !== "OK" && wsReason ? ` (${feedReasonRu(wsReason)})` : ""}
          </span>
        </div>
        <div className="top-right">
          <label className="switch">
            {ru.autoTrade}
            <input
              type="checkbox"
              checked={config.trading.auto_trade_enabled}
              onChange={(event) =>
                setConfig({ ...config, trading: { ...config.trading, auto_trade_enabled: event.target.checked } })
              }
            />
          </label>
          <button className="primary" onClick={toggleStart}>
            {status.running ? ru.stop : ru.start}
          </button>
        </div>
      </header>
      {error && <div className="alert">{error}</div>}
      {updaterStatus && updaterStatus.state !== "idle" && (
        <div className={`update-banner update-${updaterStatus.state}`}>
          <span>
            <strong>{ru.updateBanner}:</strong> {updaterStatus.message}
            {updaterStatus.version ? ` (${updaterStatus.version})` : ""}
          </span>
          <span className="update-actions">
            {updaterStatus.state === "ready" && window.spreadSystemDesktop && (
              <button
                type="button"
                className="primary"
                onClick={() => {
                  void window.spreadSystemDesktop?.installUpdateNow().then((result) => {
                    if (result && !result.ok) setError(result.message ?? "Не удалось установить обновление");
                  });
                }}
              >
                {ru.updateReadyRestart}
              </button>
            )}
            <button type="button" onClick={() => void window.spreadSystemDesktop?.checkForUpdates()}>
              {ru.checkUpdates}
            </button>
            <button type="button" onClick={() => setUpdaterStatus(null)}>
              {ru.updateDismiss}
            </button>
          </span>
        </div>
      )}

      <section className="terminal-grid">
        <aside className="left-panel panel">
          <h3>{ru.markets}</h3>
          <p className="hint">{ru.syncHint}</p>
          <label>
            {ru.marketType}
            <select
              value={config.trading.market_type}
              onChange={async (event) => {
                const marketType = event.target.value as MarketType;
                const catalog = await loadSymbols(marketType, "USDT");
                const nextQuote = catalog.quote ?? "USDT";
                setQuoteCurrency(nextQuote);
                const preferred =
                  marketType === "swap"
                    ? resolveGoldFuturesSymbol(catalog)
                    : catalog.symbols[0] ?? config.trading.symbol;
                setConfig({
                  ...config,
                  trading: { ...config.trading, market_type: marketType, symbol: preferred }
                });
              }}
            >
              <option value="spot">{ru.spot}</option>
              <option value="swap">{ru.swap}</option>
            </select>
          </label>
          {quotes.length > 0 && (
            <div className="quote-tabs">
              {quotes.map((quote) => (
                <button
                  key={quote}
                  className={quote === quoteCurrency ? "active" : ""}
                  onClick={async () => {
                    const catalog = await loadSymbols(config.trading.market_type, quote);
                    setQuoteCurrency(quote);
                    const preferred =
                      catalog.popular_symbols?.[0] ?? catalog.symbols[0] ?? config.trading.symbol;
                    setConfig({ ...config, trading: { ...config.trading, symbol: preferred } });
                  }}
                >
                  {quote}
                </button>
              ))}
            </div>
          )}
          {showGoldFuturesSection && (
            <div className="gold-futures-block">
              <h4 className="subhead gold-head">{ru.goldFutures}</h4>
              <p className="hint">{ru.goldFuturesHint}</p>
              <button
                type="button"
                className={`gold-futures-btn ${config.trading.symbol === goldFuturesSymbol ? "active" : ""}`}
                onClick={pickGoldFutures}
              >
                <span>GOLD(XAUT)USDT</span>
                <small>{goldFuturesSymbol}</small>
              </button>
              <button type="button" className="demo-preset-btn" onClick={applyDemoGoldPreset}>
                {ru.demoGoldPreset}
              </button>
              <p className="hint">{ru.demoGoldPresetHint}</p>
            </div>
          )}
          {config.trading.market_type === "swap" && quoteCurrency === "USDC" && (
            <p className="hint warn">{ru.goldFuturesUsdcHint}</p>
          )}
          <input placeholder={ru.searchPair} value={symbolSearch} onChange={(e) => setSymbolSearch(e.target.value)} />
          {popularSymbols.length > 0 && (
            <>
              <h4 className="subhead">{ru.popular}</h4>
              <div className="pair-list popular">
                {popularSymbols.map((symbol) => (
                  <button
                    key={`p-${symbol}`}
                    className={symbol === config.trading.symbol ? "active" : ""}
                    onClick={() => pickSymbol(symbol)}
                  >
                    <span>{displaySymbol(symbol, symbolCatalog)}</span>
                    <small>{symbol}</small>
                  </button>
                ))}
              </div>
            </>
          )}
          <h4 className="subhead">{ru.allPairs}</h4>
          <div className="pair-list">
            {(restSymbols.length > 0 ? restSymbols : [config.trading.symbol]).map((symbol) => (
              <button
                key={symbol}
                className={symbol === config.trading.symbol ? "active" : ""}
                onClick={() => pickSymbol(symbol)}
              >
                <span>{displaySymbol(symbol, symbolCatalog)}</span>
                <small>{symbol}</small>
              </button>
            ))}
          </div>
        </aside>

        <section className="center-panel panel">
          <h3>{ru.realtimeMetrics}</h3>
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
            <strong>{ru.liveBroadcast}</strong>
            <div className="chart-interval-tabs">
              <span className="hint">{ru.chartInterval}</span>
              {(
                [
                  ["1S", ru.chart1s],
                  ["5S", ru.chart5s],
                  ["1", ru.chart1m]
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={chartInterval === value ? "active" : ""}
                  onClick={() => setChartInterval(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <a href={mexcPlatformUrl(config.trading.symbol, config.trading.market_type, symbolCatalog)} target="_blank" rel="noreferrer">
              {ru.openOnMexc}
            </a>
          </div>
          <p className="hint">{ru.chartHint}</p>
          {pairNote && <p className="hint warn">{pairNote}</p>}
          <div className="broadcast-frame-wrap">
            <iframe
              key={`${config.trading.market_type}-${config.trading.symbol}-${chartInterval}`}
              title={ru.liveBroadcast}
              src={tradingViewEmbedUrl(config.trading.symbol, config.trading.market_type, symbolCatalog, chartInterval)}
              className="broadcast-frame"
              loading="lazy"
            />
          </div>
          <div className="metrics">
            <div>
              <span>{ru.bestBid}</span>
              <strong>{market ? market.best_bid.toFixed(4) : "0.0000"}</strong>
            </div>
            <div>
              <span>{ru.bestAsk}</span>
              <strong>{market ? market.best_ask.toFixed(4) : "0.0000"}</strong>
            </div>
            <div>
              <span>{ru.spread}</span>
              <strong>{percent.format(market?.spread ?? 0)}</strong>
            </div>
            <div>
              <span>{ru.imbalance}</span>
              <strong>{percent.format(market?.imbalance ?? 0)}</strong>
            </div>
            <div>
              <span>{ru.feedLatency}</span>
              <strong>
                {tickToRenderMs > 0
                  ? `${Math.round(tickToRenderMs)} мс`
                  : market?.clock_skew_ms != null
                    ? `${Math.round(market.clock_skew_ms)} мс`
                    : "—"}
              </strong>
            </div>
          </div>
          <div className="status-row">
            <span>
              {ru.mode}: {config.trading.mode === "paper" ? ru.paper : ru.live}
            </span>
            <span>
              {ru.auto}: {config.trading.auto_trade_enabled ? "ВКЛ" : "ВЫКЛ"}
            </span>
            <span>
              {ru.blocked}: {blockedReasonRu(status.blocked_reason)}
            </span>
          </div>

          <details className="why-silent-block panel-inner">
            <summary>{ru.whySilent}</summary>
            <p className="hint">{ru.whySilentHint}</p>
            <ul className="why-silent-list">
              <li className={status.running ? "ok-item" : "bad-item"}>{ru.whySilentStart}</li>
              <li className={config.trading.auto_trade_enabled ? "ok-item" : "bad-item"}>{ru.whySilentAuto}</li>
              <li className={wsHealth === "OK" ? "ok-item" : wsHealth === "RECOVERING" ? "warn-item" : "bad-item"}>
                {ru.whySilentFeed}
                {wsHealth !== "OK" && wsReason ? ` (${feedReasonRu(wsReason)})` : ""}
              </li>
              <li>{ru.whySilentDemo}</li>
              {status.blocked_reason && (
                <li className="bad-item">
                  {ru.blocked}: {blockedReasonRu(status.blocked_reason)}
                </li>
              )}
            </ul>
          </details>

          <details className="settings-block" open>
            <summary>{ru.settingsConnection}</summary>
            <div className="settings">
              <label>
                {ru.apiKey}
                <input
                  value={config.exchange.api_key}
                  onChange={(e) => setConfig({ ...config, exchange: { ...config.exchange, api_key: e.target.value } })}
                />
              </label>
              <label>
                {ru.apiSecret}
                <input
                  type="password"
                  value={config.exchange.api_secret}
                  onChange={(e) => setConfig({ ...config, exchange: { ...config.exchange, api_secret: e.target.value } })}
                />
              </label>
              <label>
                {ru.apiPassword}
                <input
                  type="password"
                  value={config.exchange.password}
                  onChange={(e) => setConfig({ ...config, exchange: { ...config.exchange, password: e.target.value } })}
                />
              </label>
              <label>
                {ru.tradingMode}
                <select
                  value={config.trading.mode}
                  onChange={(e) => setConfig({ ...config, trading: { ...config.trading, mode: e.target.value as "paper" | "live" } })}
                >
                  <option value="paper">{ru.paper}</option>
                  <option value="live">{ru.live}</option>
                </select>
              </label>
              <label className="switch">
                {ru.enableLiveOrders}
                <input
                  type="checkbox"
                  checked={config.trading.live_trading_enabled}
                  onChange={(e) => setConfig({ ...config, trading: { ...config.trading, live_trading_enabled: e.target.checked } })}
                />
              </label>
              <label className="switch">
                {ru.demoRelaxed}
                <input
                  type="checkbox"
                  checked={Boolean(config.trading.demo_relaxed_signals)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      trading: { ...config.trading, demo_relaxed_signals: e.target.checked }
                    })
                  }
                />
              </label>
              <label>
                {ru.orderSize}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.trading.order_size)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      trading: {
                        ...config.trading,
                        order_size: parseLocaleNumber(e.target.value, config.trading.order_size)
                      }
                    })
                  }
                />
              </label>
            </div>
          </details>

          <details className="settings-block">
            <summary>{ru.scalp}</summary>
            <div className="settings">
              <label>
                {ru.spreadMin}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.simple_scalp?.spread_min ?? 0.0002)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      simple_scalp: {
                        ...config.simple_scalp!,
                        spread_min: parseLocaleNumber(e.target.value, config.simple_scalp?.spread_min ?? 0.0002)
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.imbalanceMin}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.simple_scalp?.imbalance_min ?? 0.2)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      simple_scalp: {
                        ...config.simple_scalp!,
                        imbalance_min: parseLocaleNumber(e.target.value, config.simple_scalp?.imbalance_min ?? 0.2)
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.aggressionMin}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.simple_scalp?.aggression_min ?? 0.15)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      simple_scalp: {
                        ...config.simple_scalp!,
                        aggression_min: parseLocaleNumber(e.target.value, config.simple_scalp?.aggression_min ?? 0.15)
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.staleOrderSec}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.simple_scalp?.stale_order_after_seconds ?? 1.5)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      simple_scalp: {
                        ...config.simple_scalp!,
                        stale_order_after_seconds: parseLocaleNumber(
                          e.target.value,
                          config.simple_scalp?.stale_order_after_seconds ?? 1.5
                        )
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.replaceMoveBps}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.simple_scalp?.replace_move_bps ?? 3)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      simple_scalp: {
                        ...config.simple_scalp!,
                        replace_move_bps: parseLocaleNumber(e.target.value, config.simple_scalp?.replace_move_bps ?? 3)
                      }
                    })
                  }
                />
              </label>
            </div>
          </details>

          <details className="settings-block">
            <summary>{ru.strategy}</summary>
            <div className="settings">
              <label>
                {ru.maxHoldingSec}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.strategy.max_holding_seconds ?? 8)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      strategy: {
                        ...config.strategy,
                        max_holding_seconds: parseLocaleNumber(e.target.value, config.strategy.max_holding_seconds ?? 8)
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.maxOpenOrders}
                <input
                  type="text"
                  inputMode="numeric"
                  value={String(config.strategy.max_open_orders_per_symbol ?? 1)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      strategy: {
                        ...config.strategy,
                        max_open_orders_per_symbol: Math.max(
                          1,
                          Math.round(parseLocaleNumber(e.target.value, config.strategy.max_open_orders_per_symbol ?? 1))
                        )
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.entryCooldownSec}
                <input
                  type="text"
                  inputMode="numeric"
                  value={String(config.strategy.entry_cooldown_seconds ?? 5)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      strategy: {
                        ...config.strategy,
                        entry_cooldown_seconds: Math.max(
                          0,
                          Math.round(parseLocaleNumber(e.target.value, config.strategy.entry_cooldown_seconds ?? 5))
                        )
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.imbalanceExit}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.strategy.imbalance_exit_threshold ?? 0.12)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      strategy: {
                        ...config.strategy,
                        imbalance_exit_threshold: parseLocaleNumber(
                          e.target.value,
                          config.strategy.imbalance_exit_threshold ?? 0.12
                        )
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.tapeAggressionEntry}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.strategy.tape_aggression_entry_threshold ?? 0.25)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      strategy: {
                        ...config.strategy,
                        tape_aggression_entry_threshold: parseLocaleNumber(
                          e.target.value,
                          config.strategy.tape_aggression_entry_threshold ?? 0.25
                        )
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.marketStaleSec}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.strategy.market_data_stale_after_seconds ?? 2)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      strategy: {
                        ...config.strategy,
                        market_data_stale_after_seconds: parseLocaleNumber(
                          e.target.value,
                          config.strategy.market_data_stale_after_seconds ?? 2
                        )
                      }
                    })
                  }
                />
              </label>
            </div>
          </details>

          <details className="settings-block">
            <summary>{ru.risk}</summary>
            <div className="settings">
              <label>
                {ru.maxDailyLoss}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.risk.max_daily_loss)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      risk: { ...config.risk, max_daily_loss: parseLocaleNumber(e.target.value, config.risk.max_daily_loss) }
                    })
                  }
                />
              </label>
              <label>
                {ru.maxPositionSize}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.risk.max_position_size)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      risk: {
                        ...config.risk,
                        max_position_size: parseLocaleNumber(e.target.value, config.risk.max_position_size)
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.maxInventory}
                <input
                  type="text"
                  inputMode="decimal"
                  value={String(config.risk.max_inventory_exposure)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      risk: {
                        ...config.risk,
                        max_inventory_exposure: parseLocaleNumber(e.target.value, config.risk.max_inventory_exposure)
                      }
                    })
                  }
                />
              </label>
              <label>
                {ru.cooldownAfterLoss}
                <input
                  type="text"
                  inputMode="numeric"
                  value={String(config.risk.cooldown_after_loss_seconds)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      risk: {
                        ...config.risk,
                        cooldown_after_loss_seconds: Math.max(
                          0,
                          Math.round(parseLocaleNumber(e.target.value, config.risk.cooldown_after_loss_seconds))
                        )
                      }
                    })
                  }
                />
              </label>
            </div>
          </details>

          <button className="primary save-wide" onClick={saveConfig} disabled={saving}>
            {saving ? ru.saving : ru.saveConfig}
          </button>

          <div className="dry-run">
            <h4>{ru.dryRun}</h4>
            {dryRunOrders.length === 0 && <p>{ru.noDryRun}</p>}
            {dryRunOrders.slice(-12).reverse().map((order) => (
              <div key={order.id} className="dry-item">
                <span>{order.timestamp}</span>
                <strong>
                  {order.side.toUpperCase()} {order.size}
                </strong>
                <span>
                  @ {order.price.toFixed(4)} · {order.status}
                </span>
              </div>
            ))}
          </div>
        </section>

        <aside className="right-panel panel">
          <h3>{ru.orderBook}</h3>
          <div className="book">
            <div className="book-side">
              <h4>{ru.asks}</h4>
              {(market?.asks ?? []).slice(0, 10).map((level) => (
                <div key={`a-${level.price}-${level.size}`} className="level sell">
                  <span>{level.price.toFixed(4)}</span>
                  <span>{level.size.toFixed(4)}</span>
                </div>
              ))}
            </div>
            <div className="book-side">
              <h4>{ru.bids}</h4>
              {(market?.bids ?? []).slice(0, 10).map((level) => (
                <div key={`b-${level.price}-${level.size}`} className="level buy">
                  <span>{level.price.toFixed(4)}</span>
                  <span>{level.size.toFixed(4)}</span>
                </div>
              ))}
            </div>
          </div>
          <h3>{ru.liveTrades}</h3>
          <div className="tape">
            {(market?.recent_trades ?? []).slice(-60).reverse().map((trade) => (
              <div key={`${trade.timestamp}-${trade.price}-${trade.size}`} className={`tape-item ${trade.side}`}>
                <span>{new Date(trade.timestamp).toLocaleTimeString("ru-RU")}</span>
                <strong>{trade.price.toFixed(4)}</strong>
                <span>{trade.size.toFixed(4)}</span>
              </div>
            ))}
          </div>
          <div className="mini-pnl">
            {ru.spread}: {percent.format(market?.spread ?? 0)} · {ru.imbalance}: {percent.format(market?.imbalance ?? 0)}
          </div>
        </aside>
      </section>
    </main>
  );
}
