export type TradingMode = "paper" | "live";
export type ExchangeName = "mexc";
export type MarketType = "spot" | "swap";

export interface AppConfig {
  exchange: {
    name: ExchangeName;
    api_key: string;
    api_secret: string;
    password: string;
    sandbox: boolean;
  };
  trading: {
    mode: TradingMode;
    market_type: MarketType;
    symbol: string;
    order_size: number;
    cycle_interval_seconds: number;
    live_trading_enabled: boolean;
    auto_trade_enabled: boolean;
    use_realtime_dom_engine?: boolean;
    demo_relaxed_signals?: boolean;
  };
  fees: {
    maker: number;
    taker: number;
  };
  strategy: {
    min_edge: number;
    volatility_threshold: number;
    imbalance_limit: number;
    min_liquidity: number;
    volatility_window: number;
    max_orderbook_age_seconds?: number;
    max_open_orders_per_symbol?: number;
    entry_cooldown_seconds?: number;
    imbalance_exit_threshold?: number;
    tape_aggression_entry_threshold?: number;
    market_data_stale_after_seconds?: number;
    max_holding_seconds?: number;
  };
  risk: {
    max_daily_loss: number;
    max_inventory_exposure: number;
    max_position_size: number;
    cooldown_after_loss_seconds: number;
  };
  simple_scalp?: {
    spread_min: number;
    imbalance_min: number;
    aggression_min: number;
    stale_order_after_seconds: number;
    replace_move_bps: number;
  };
}

export interface BotStatus {
  running: boolean;
  mode: TradingMode;
  exchange: string;
  symbol: string;
  last_error: string | null;
  last_update: string | null;
  spread: number;
  edge: number;
  volatility: number;
  imbalance: number;
  blocked_reason: string | null;
  dry_run_orders?: DryRunOrder[];
}

export interface Trade {
  id: number;
  timestamp: string;
  symbol: string;
  side: "buy" | "sell";
  price: number;
  size: number;
  pnl: number;
  fee: number;
  exchange: string;
}

export interface PnlSummary {
  total_pnl: number;
  daily_pnl: number;
  net_pnl: number;
  gross_pnl: number;
  fees: number;
  winrate: number;
  profit_factor: number;
  trade_count: number;
  equity_curve: Array<{ timestamp: string; equity: number }>;
}

export interface LiveMessage {
  type: "snapshot" | "live" | "status" | "config" | "error" | "market" | "orders" | "dry_run" | "sync";
  status?: BotStatus;
  pnl?: PnlSummary;
  trades?: Trade[];
  trade?: Trade | null;
  config?: AppConfig;
  message?: string;
  metrics?: Record<string, number>;
  market?: MarketStateEnvelope;
  state?: MarketState;
  orders?: Array<Record<string, unknown>>;
  dry_run_orders?: DryRunOrder[];
  event?: DryRunOrder;
  market_data?: Record<string, unknown>;
  dom_delta?: DomDelta;
  tape_trade?: TapeTrade;
}

export interface AppLog {
  timestamp: string;
  level: string;
  message: string;
}

export interface SymbolMeta {
  display: string;
  quote: string;
  kind: string;
  mexc_url: string;
  tradingview: string;
  note: string;
}

export interface SymbolListResponse {
  exchange: "mexc";
  market_type: MarketType;
  quotes: string[];
  quote: string | null;
  symbols_by_quote: Record<string, string[]>;
  symbols: string[];
  popular_symbols?: string[];
  symbols_meta?: Record<string, SymbolMeta>;
  /** CCXT symbol for MEXC GOLD(XAUT)USDT perpetual when market_type is swap */
  gold_futures_symbol?: string | null;
}

export interface MarketBookLevel {
  price: number;
  size: number;
}

export interface MarketTradePrint {
  price: number;
  size: number;
  side: "buy" | "sell";
  timestamp: string;
}

export interface MarketState {
  exchange: string;
  market_type: MarketType;
  symbol: string;
  best_bid: number;
  best_ask: number;
  spread: number;
  imbalance: number;
  bids: MarketBookLevel[];
  asks: MarketBookLevel[];
  recent_trades: MarketTradePrint[];
  ws_status: string;
  ws_reason: string;
  feed_state?: "OK" | "DELAYED" | "DESYNC" | "RECOVERING";
  last_update: string | null;
  sequence: number | null;
  clock_skew_ms?: number;
  tape_velocity_1s?: number;
  buy_aggression_rate?: number;
  sell_aggression_rate?: number;
  delta_velocity?: number;
  dom_queue_depth?: number;
  tape_queue_depth?: number;
  resync_count?: number;
  desync_count?: number;
  reconnect_count?: number;
  ui_drop_rate?: number;
  book_apply_latency_ms?: number;
  candles_1m?: CandleBar[];
}

export interface MarketStateEnvelope {
  health: Record<string, unknown>;
  exchange: string;
  market_type: MarketType;
  symbol: string;
  best_bid: number;
  best_ask: number;
  spread: number;
  imbalance: number;
  bids: MarketBookLevel[];
  asks: MarketBookLevel[];
  recent_trades: MarketTradePrint[];
  ws_status: string;
  ws_reason: string;
  feed_state?: "OK" | "DELAYED" | "DESYNC" | "RECOVERING";
  last_update: string | null;
  sequence: number | null;
  clock_skew_ms?: number;
  tape_velocity_1s?: number;
  buy_aggression_rate?: number;
  sell_aggression_rate?: number;
  delta_velocity?: number;
  dom_queue_depth?: number;
  tape_queue_depth?: number;
  resync_count?: number;
  desync_count?: number;
  reconnect_count?: number;
  ui_drop_rate?: number;
  book_apply_latency_ms?: number;
  candles_1m?: CandleBar[];
}

export interface CandleBar {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface DomDelta {
  type: "dom_delta";
  symbol: string;
  market_type: MarketType;
  sequence?: number;
  ts_exchange?: number;
  ts_local: number;
  spread?: number;
  best_bid?: number;
  best_ask?: number;
  updated_bids: Array<[number, number]>;
  updated_asks: Array<[number, number]>;
  removed_bids?: number[];
  removed_asks?: number[];
  book_health: string;
}

export interface TapeTrade {
  type: "tape_trade";
  symbol: string;
  market_type: MarketType;
  trade_id?: string;
  side: "buy" | "sell";
  aggressor?: "buyer" | "seller";
  price: number;
  size: number;
  notional?: number;
  ts_exchange?: number;
  ts_local: number;
}

export interface DryRunOrder {
  id: string;
  timestamp: string;
  symbol?: string;
  market_type?: string;
  side: "buy" | "sell";
  price: number;
  size: number;
  reason: string;
  status: string;
  closed_at?: string;
  exit_price?: number;
  exit_reason?: string;
}
