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

    name: Literal["binance", "bybit", "mexc"] = "binance"
    api_key: str = ""
    api_secret: str = ""
    password: str = ""
    sandbox: bool = True


class TradingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["paper", "live"] = "paper"
    symbol: str = "BTC/USDT"
    order_size: float = Field(default=0.001, gt=0)
    cycle_interval_seconds: float = Field(default=1.0, ge=0.2, le=60)
    live_trading_enabled: bool = False

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

    min_edge: float = Field(default=0.001, ge=0)
    volatility_threshold: float = Field(default=0.02, ge=0)
    imbalance_limit: float = Field(default=0.7, ge=0, le=1)
    min_liquidity: float = Field(default=1000.0, ge=0)
    volatility_window: int = Field(default=20, ge=2, le=500)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_daily_loss: float = Field(default=100.0, ge=0)
    max_inventory_exposure: float = Field(default=1000.0, ge=0)
    max_position_size: float = Field(default=0.01, gt=0)
    cooldown_after_loss_seconds: int = Field(default=60, ge=0, le=86400)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    fees: FeeConfig = Field(default_factory=FeeConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)

    @field_validator("trading")
    @classmethod
    def live_requires_explicit_enablement(cls, trading: TradingConfig) -> TradingConfig:
        if trading.mode == "live" and not trading.live_trading_enabled:
            raise ValueError("live mode requires live_trading_enabled=true")
        return trading


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
                payload = json.loads(self.path.read_text(encoding="utf-8"))
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
