from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import ccxt

logger = logging.getLogger(__name__)

from .config import AppConfig
from .database import Fill, OrderIntent, encode_raw
from .credentials import credential_store
from .strategy import MarketSnapshot, OrderBookLevel, TapePrint


@dataclass(frozen=True)
class ExchangeOrder:
    exchange: str
    market_type: str
    symbol: str
    exchange_order_id: str | None
    client_order_id: str | None
    status: str
    side: str
    order_type: str
    requested_size: float
    filled_size: float
    remaining_size: float
    average_price: float | None
    raw_payload: dict[str, Any]


class ExchangeAdapter:
    def __init__(self) -> None:
        self._client: Any | None = None
        self._signature: tuple[str, str, str, str, bool, str] | None = None

    def _build_client(self, config: AppConfig) -> Any:
        creds = credential_store.get(config.exchange.name)
        api_key = creds.api_key if creds else config.exchange.api_key
        api_secret = creds.api_secret if creds else config.exchange.api_secret
        password = creds.password if creds else config.exchange.password
        signature = (config.exchange.name, api_key, api_secret, password, config.exchange.sandbox, config.trading.market_type)
        if self._client is not None and self._signature == signature:
            return self._client
        exchange_cls = getattr(ccxt, config.exchange.name)
        client = exchange_cls({
            "apiKey": api_key,
            "secret": api_secret,
            "password": password or None,
            "enableRateLimit": True,
            "options": {"defaultType": "swap" if config.trading.market_type == "swap" else "spot"},
        })
        if config.exchange.sandbox and hasattr(client, "set_sandbox_mode"):
            test_urls = (getattr(client, "urls", None) or {}).get("test")
            if test_urls:
                client.set_sandbox_mode(True)
            else:
                logger.warning(
                    "%s has no CCXT sandbox/test API URLs; using production endpoints",
                    config.exchange.name,
                )
        self._client = client
        self._signature = signature
        return client

    async def fetch_order_book(self, config: AppConfig) -> MarketSnapshot:
        client = self._build_client(config)
        depth = config.strategy.orderbook_depth_levels
        book = await asyncio.to_thread(client.fetch_order_book, config.trading.symbol, limit=depth)
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        if not bids or not asks:
            raise RuntimeError("order book has no bids or asks")
        bid, bid_size = float(bids[0][0]), float(bids[0][1])
        ask, ask_size = float(asks[0][0]), float(asks[0][1])
        bid_levels = [OrderBookLevel(float(price), float(size)) for price, size, *_ in bids[:depth]]
        ask_levels = [OrderBookLevel(float(price), float(size)) for price, size, *_ in asks[:depth]]
        liquidity = sum(level.notional for level in bid_levels[:5] + ask_levels[:5])
        return MarketSnapshot(
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            liquidity=liquidity,
            timestamp=datetime.now(UTC).isoformat(),
            bids=bid_levels,
            asks=ask_levels,
            recent_trades=await self.fetch_recent_trades(config),
        )

    async def fetch_recent_trades(self, config: AppConfig) -> list[TapePrint]:
        client = self._build_client(config)
        has_fetch_trades = getattr(client, "has", {}).get("fetchTrades", True)
        if not has_fetch_trades:
            return []
        try:
            trades = await asyncio.to_thread(client.fetch_trades, config.trading.symbol, None, 100)
        except Exception:
            return []
        parsed: list[TapePrint] = []
        for trade in trades:
            side = str(trade.get("side") or "").lower()
            if side not in {"buy", "sell"}:
                continue
            parsed.append(
                TapePrint(
                    price=float(trade.get("price") or 0.0),
                    size=float(trade.get("amount") or 0.0),
                    side=side,
                    timestamp=self._trade_timestamp(trade),
                )
            )
        return parsed

    async def submit_order(self, config: AppConfig, intent: OrderIntent) -> ExchangeOrder:
        if not config.trading.live_trading_enabled:
            raise RuntimeError("live trading blocked: live_trading_enabled is false")
        if not config.exchange.api_key or not config.exchange.api_secret:
            raise RuntimeError("live trading requires API key and secret")
        client = self._build_client(config)
        params = {"clientOrderId": intent.client_order_id}
        price = intent.requested_price if intent.order_type == "limit" else None
        order = await asyncio.to_thread(
            client.create_order,
            intent.symbol,
            intent.order_type,
            intent.side,
            intent.requested_size,
            price,
            params,
        )
        normalized = self._normalize_order(config, order, intent)
        if normalized.exchange_order_id is None:
            return ExchangeOrder(
                exchange=intent.exchange,
                market_type=intent.market_type,
                symbol=intent.symbol,
                exchange_order_id=None,
                client_order_id=intent.client_order_id,
                status="UNKNOWN",
                side=intent.side,
                order_type=intent.order_type,
                requested_size=intent.requested_size,
                filled_size=0.0,
                remaining_size=intent.requested_size,
                average_price=None,
                raw_payload=order,
            )
        return normalized

    async def fetch_order_status(self, config: AppConfig, exchange_order_id: str, symbol: str) -> ExchangeOrder:
        client = self._build_client(config)
        order = await asyncio.to_thread(client.fetch_order, exchange_order_id, symbol)
        return self._normalize_order(config, order)

    async def fetch_open_orders(self, config: AppConfig, symbol: str | None = None) -> list[ExchangeOrder]:
        client = self._build_client(config)
        orders = await asyncio.to_thread(client.fetch_open_orders, symbol or config.trading.symbol)
        return [self._normalize_order(config, order) for order in orders]

    async def fetch_my_trades(self, config: AppConfig, symbol: str | None = None, since: int | None = None) -> list[Fill]:
        client = self._build_client(config)
        trades = await asyncio.to_thread(client.fetch_my_trades, symbol or config.trading.symbol, since)
        fills: list[Fill] = []
        for trade in trades:
            order_id = str(trade.get("order") or trade.get("orderId") or "")
            trade_id = str(trade.get("id") or trade.get("tradeId") or "")
            if not order_id or not trade_id:
                continue
            fee = trade.get("fee") or {}
            fills.append(
                Fill(
                    exchange=config.exchange.name,
                    market_type=config.trading.market_type,
                    symbol=str(trade.get("symbol") or symbol or config.trading.symbol).upper(),
                    exchange_order_id=order_id,
                    exchange_trade_id=trade_id,
                    side=str(trade.get("side") or "").lower(),
                    price=float(trade.get("price") or 0),
                    size=float(trade.get("amount") or 0),
                    fee=float(fee.get("cost") or 0) if isinstance(fee, dict) else 0.0,
                    fee_currency=str(fee.get("currency") or "") if isinstance(fee, dict) else "",
                    liquidity=trade.get("takerOrMaker"),
                    timestamp=self._trade_timestamp(trade),
                    raw_payload=encode_raw(trade),
                )
            )
        return fills

    async def fetch_balances(self, config: AppConfig) -> dict[str, Any]:
        client = self._build_client(config)
        return await asyncio.to_thread(client.fetch_balance)

    async def fetch_positions(self, config: AppConfig) -> list[dict[str, Any]]:
        client = self._build_client(config)
        if not hasattr(client, "fetch_positions"):
            return []
        try:
            return await asyncio.to_thread(client.fetch_positions, [config.trading.symbol])
        except Exception:
            return []

    async def cancel_order(self, config: AppConfig, exchange_order_id: str, symbol: str) -> ExchangeOrder:
        client = self._build_client(config)
        order = await asyncio.to_thread(client.cancel_order, exchange_order_id, symbol)
        return self._normalize_order(config, order)

    async def fetch_symbol_catalog(self, config: AppConfig, market_type: str) -> dict[str, object]:
        client = self._build_client(config)
        markets = await asyncio.to_thread(client.load_markets)
        symbols_by_quote: dict[str, list[str]] = {}
        for market in markets.values():
            if not market.get("active", True):
                continue
            if market_type == "swap":
                if not market.get("swap"):
                    continue
            elif market_type == "spot":
                if not market.get("spot"):
                    continue
            else:
                continue
            symbol = str(market.get("symbol") or "").upper()
            quote = str(market.get("quote") or "").upper()
            if not symbol or not quote:
                continue
            symbols_by_quote.setdefault(quote, []).append(symbol)
        for quote in symbols_by_quote:
            symbols_by_quote[quote] = sorted(set(symbols_by_quote[quote]))
        quotes = sorted(symbols_by_quote.keys(), key=lambda q: (q != "USDT", q))
        return {"quotes": quotes, "symbols_by_quote": symbols_by_quote}

    async def fetch_symbols(self, config: AppConfig, market_type: str, quote: str | None = None) -> list[str]:
        catalog = await self.fetch_symbol_catalog(config, market_type)
        symbols_by_quote = catalog["symbols_by_quote"]
        assert isinstance(symbols_by_quote, dict)
        if quote:
            normalized = quote.upper()
            return list(symbols_by_quote.get(normalized, []))
        flat: list[str] = []
        for items in symbols_by_quote.values():
            flat.extend(items)
        return sorted(set(flat))

    @staticmethod
    def _normalize_order(config: AppConfig, order: dict[str, Any], intent: OrderIntent | None = None) -> ExchangeOrder:
        requested_size = float(order.get("amount") or (intent.requested_size if intent else 0.0))
        filled_size = float(order.get("filled") or 0.0)
        remaining_size = float(order.get("remaining") if order.get("remaining") is not None else max(requested_size - filled_size, 0.0))
        return ExchangeOrder(
            exchange=config.exchange.name,
            market_type=config.trading.market_type,
            symbol=str(order.get("symbol") or (intent.symbol if intent else config.trading.symbol)).upper(),
            exchange_order_id=str(order["id"]) if order.get("id") else None,
            client_order_id=str(order.get("clientOrderId") or (intent.client_order_id if intent else "")) or None,
            status=ExchangeAdapter._normalize_status(str(order.get("status") or "unknown"), requested_size, filled_size, remaining_size),
            side=str(order.get("side") or (intent.side if intent else "")).lower(),
            order_type=str(order.get("type") or (intent.order_type if intent else config.trading.order_type)).lower(),
            requested_size=requested_size,
            filled_size=filled_size,
            remaining_size=remaining_size,
            average_price=float(order["average"]) if order.get("average") is not None else None,
            raw_payload=order,
        )

    @staticmethod
    def _normalize_status(status: str, requested_size: float, filled_size: float, remaining_size: float) -> str:
        status = status.lower()
        if status in {"closed", "filled"}:
            return "FILLED"
        if status in {"canceled", "cancelled"}:
            return "CANCELLED"
        if status in {"rejected", "expired"}:
            return "REJECTED"
        if filled_size > 0 and remaining_size > 0:
            return "PARTIAL"
        if status in {"open", "new"}:
            return "OPEN"
        if requested_size > 0 and filled_size >= requested_size:
            return "FILLED"
        return "UNKNOWN"

    @staticmethod
    def _trade_timestamp(trade: dict[str, Any]) -> str:
        if trade.get("datetime"):
            return str(trade["datetime"])
        if trade.get("timestamp"):
            return datetime.fromtimestamp(float(trade["timestamp"]) / 1000, tz=UTC).isoformat()
        return datetime.now(UTC).isoformat()


exchange_adapter = ExchangeAdapter()
