export type TradingMode = "paper" | "live";
export type ExchangeName = "binance" | "bybit" | "mexc";

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
    symbol: string;
    order_size: number;
    cycle_interval_seconds: number;
    live_trading_enabled: boolean;
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
  };
  risk: {
    max_daily_loss: number;
    max_inventory_exposure: number;
    max_position_size: number;
    cooldown_after_loss_seconds: number;
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
  type: "snapshot" | "live" | "status" | "config" | "error";
  status?: BotStatus;
  pnl?: PnlSummary;
  trades?: Trade[];
  trade?: Trade | null;
  config?: AppConfig;
  message?: string;
  metrics?: Record<string, number>;
}

export interface AppLog {
  timestamp: string;
  level: string;
  message: string;
}
