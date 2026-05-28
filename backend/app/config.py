from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("SPREAD_SYSTEM_DATA_DIR", PROJECT_ROOT / "data"))
CONFIG_PATH = DATA_DIR / "config.json"


class ExchangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["mexc"] = "mexc"
    api_key: str = ""
    api_secret: str = ""
    password: str = ""
    sandbox: bool = False


class TradingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["paper", "live"] = "paper"
    market_type: Literal["spot", "swap"] = "swap"
    symbol: str = "BTC/USDT"
    order_size: float = Field(default=0.001, gt=0)
    order_type: Literal["market", "limit"] = "market"
    cycle_interval_seconds: float = Field(default=1.0, ge=0.2, le=60)
    sync_interval_seconds: float = Field(default=2.0, ge=0.5, le=300)
    live_trading_enabled: bool = False
    auto_trade_enabled: bool = False
    use_realtime_dom_engine: bool = True
    require_validation: bool = True

    @field_validator("symbol")
    @classmethod
    def symbol_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbol must not be empty")
        return value.strip().upper()


class FeeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maker: float = Field(default=0.001, ge=0, le=0.1)
    taker: float = Field(default=0.001, ge=0, le=0.1)


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_edge: float = Field(default=0.0, ge=0)
    volatility_threshold: float = Field(default=0.02, ge=0)
    imbalance_limit: float = Field(default=0.35, ge=0, le=1)
    min_liquidity: float = Field(default=1000.0, ge=0)
    volatility_window: int = Field(default=20, ge=2, le=500)
    max_orderbook_age_seconds: float = Field(default=3.0, ge=0.1, le=60)
    slippage_buffer: float = Field(default=0.0005, ge=0, le=0.1)
    max_open_orders_per_symbol: int = Field(default=1, ge=1, le=20)
    entry_cooldown_seconds: int = Field(default=5, ge=0, le=86400)
    orderbook_depth_levels: int = Field(default=10, ge=3, le=50)
    wall_multiplier: float = Field(default=3.0, ge=1.0, le=100.0)
    wall_proximity_bps: float = Field(default=15.0, ge=0.0, le=500.0)
    min_wall_notional: float = Field(default=500.0, ge=0.0)
    tape_window_seconds: float = Field(default=3.0, ge=0.5, le=60.0)
    tape_aggression_entry_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    imbalance_exit_threshold: float = Field(default=0.12, ge=0.0, le=1.0)
    tape_aggression_exit_threshold: float = Field(default=0.10, ge=0.0, le=1.0)
    min_tape_notional: float = Field(default=250.0, ge=0.0)
    momentum_burst_multiplier: float = Field(default=1.5, ge=1.0, le=20.0)
    max_holding_seconds: float = Field(default=8.0, ge=1.0, le=300.0)
    websocket_silence_seconds: float = Field(default=5.0, ge=0.5, le=120.0)
    market_data_stale_after_seconds: float = Field(default=2.0, ge=0.1, le=60.0)
    tape_silence_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    max_event_delay_ms: float = Field(default=1500.0, ge=1.0, le=60000.0)
    trade_book_validation_tolerance_bps: float = Field(default=10.0, ge=0.0, le=1000.0)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_daily_loss: float = Field(default=100.0, ge=0)
    max_inventory_exposure: float = Field(default=1000.0, ge=0)
    max_position_size: float = Field(default=0.01, gt=0)
    cooldown_after_loss_seconds: int = Field(default=60, ge=0, le=86400)


class SimpleScalpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spread_min: float = Field(default=0.0002, ge=0)
    imbalance_min: float = Field(default=0.2, ge=0.0, le=1.0)
    aggression_min: float = Field(default=0.15, ge=0.0, le=1.0)
    stale_order_after_seconds: float = Field(default=1.5, ge=0.2, le=60.0)
    replace_move_bps: float = Field(default=3.0, ge=0.0, le=100.0)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    fees: FeeConfig = Field(default_factory=FeeConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    simple_scalp: SimpleScalpConfig = Field(default_factory=SimpleScalpConfig)

    @field_validator("trading")
    @classmethod
    def live_requires_explicit_enablement(cls, trading: TradingConfig) -> TradingConfig:
        if trading.mode == "live" and not trading.live_trading_enabled:
            raise ValueError("live mode requires live_trading_enabled=true")
        return trading


def migrate_config_payload(payload: dict) -> dict:
    """Force MEXC-only deployment; coerce legacy binance/bybit configs."""
    exchange = dict(payload.get("exchange") or {})
    exchange["name"] = "mexc"
    exchange["sandbox"] = False
    payload["exchange"] = exchange
    return payload


class ConfigService:
    """Loads and persists config.json with mtime-based hot reload."""

    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._lock = RLock()
        self._config: AppConfig | None = None
        self._mtime: float | None = None

    def ensure_exists(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(AppConfig())

    def load(self, force: bool = False) -> AppConfig:
        with self._lock:
            self.ensure_exists()
            mtime = self.path.stat().st_mtime
            if not force and self._config is not None and self._mtime == mtime:
                return self._config
            try:
                payload = migrate_config_payload(json.loads(self.path.read_text(encoding="utf-8")))
                self._config = AppConfig.model_validate(payload)
                self._mtime = mtime
                return self._config
            except Exception:
                logger.exception("Failed to load config from %s", self.path)
                raise

    def save(self, config: AppConfig) -> AppConfig:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(config.model_dump(), indent=2) + "\n", encoding="utf-8")
            self._config = config
            self._mtime = self.path.stat().st_mtime
            return config


config_service = ConfigService()
