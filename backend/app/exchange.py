from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import ccxt

from .config import AppConfig
from .strategy import MarketSnapshot


@dataclass(frozen=True)
class ExecutionResult:
    symbol: str
    side: str
    price: float
    size: float
    fee: float
    pnl: float
    exchange: str
    mode: str
    order_id: str | None = None


class ExchangeAdapter:
    def __init__(self) -> None:
        self._client: Any | None = None
        self._signature: tuple[str, str, str, str, bool] | None = None

    def _build_client(self, config: AppConfig) -> Any:
        signature = (config.exchange.name, config.exchange.api_key, config.exchange.api_secret, config.exchange.password, config.exchange.sandbox)
        if self._client is not None and self._signature == signature:
            return self._client
        exchange_cls = getattr(ccxt, config.exchange.name)
        client = exchange_cls({
            "apiKey": config.exchange.api_key,
            "secret": config.exchange.api_secret,
            "password": config.exchange.password or None,
            "enableRateLimit": True,
        })
        if config.exchange.sandbox and hasattr(client, "set_sandbox_mode"):
            client.set_sandbox_mode(True)
        self._client = client
        self._signature = signature
        return client

    async def fetch_order_book(self, config: AppConfig) -> MarketSnapshot:
        client = self._build_client(config)
        book = await asyncio.to_thread(client.fetch_order_book, config.trading.symbol, limit=10)
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        if not bids or not asks:
            raise RuntimeError("order book has no bids or asks")
        bid, bid_size = float(bids[0][0]), float(bids[0][1])
        ask, ask_size = float(asks[0][0]), float(asks[0][1])
        liquidity = sum(float(price) * float(size) for price, size, *_ in bids[:5] + asks[:5])
        return MarketSnapshot(bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size, liquidity=liquidity)

    async def execute(self, config: AppConfig, side: str, price: float, edge: float) -> ExecutionResult:
        size = config.trading.order_size
        fee_rate = config.fees.taker if side == "buy" else config.fees.maker
        fee = price * size * fee_rate
        if config.trading.mode == "paper":
            pnl = edge * price * size
            return ExecutionResult(config.trading.symbol, side, price, size, fee, pnl, config.exchange.name, "paper")
        if not config.trading.live_trading_enabled:
            raise RuntimeError("live trading blocked: live_trading_enabled is false")
        if not config.exchange.api_key or not config.exchange.api_secret:
            raise RuntimeError("live trading requires API key and secret")
        client = self._build_client(config)
        order = await asyncio.to_thread(client.create_order, config.trading.symbol, "market", side, size)
        average = float(order.get("average") or order.get("price") or price)
        filled = float(order.get("filled") or size)
        order_fee = order.get("fee") or {}
        realized_fee = float(order_fee.get("cost") or average * filled * fee_rate)
        return ExecutionResult(config.trading.symbol, side, average, filled, realized_fee, 0.0, config.exchange.name, "live", str(order.get("id")) if order.get("id") else None)


exchange_adapter = ExchangeAdapter()
