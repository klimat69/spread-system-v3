from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

import websockets
from pydantic import BaseModel, Field, ValidationError

from .config import AppConfig
from .database import trade_repository
from .exchange import exchange_adapter
from .market_state import MarketState
from .strategy import MarketSnapshot, OrderBookLevel, TapePrint

logger = logging.getLogger(__name__)


class DomDeltaPayload(BaseModel):
    type: str = "dom_delta"
    symbol: str
    market_type: str
    ts_exchange: int | None = None
    ts_local: int
    updated_bids: list[list[float]] = Field(default_factory=list)
    updated_asks: list[list[float]] = Field(default_factory=list)
    book_health: str
    sequence: int | None = None
    removed_bids: list[float] = Field(default_factory=list)
    removed_asks: list[float] = Field(default_factory=list)
    spread: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None


class TapeTradePayload(BaseModel):
    type: str = "tape_trade"
    symbol: str
    market_type: str
    side: str
    price: float
    size: float
    ts_exchange: int | None = None
    ts_local: int
    aggressor: str | None = None
    trade_id: str | None = None
    notional: float | None = None


def monotonic_ns() -> int:
    return time.monotonic_ns()


def ns_to_ms(ns: int) -> float:
    return ns / 1_000_000


def symbol_stream(symbol: str) -> str:
    return symbol.replace("/", "").replace(":", "").lower()


def symbol_upper_no_sep(symbol: str) -> str:
    return symbol.replace("/", "").replace(":", "").upper()


def mexc_contract_symbol(symbol: str) -> str:
    """CCXT BTC/USDT or BTC/USDT:USDT -> MEXC futures BTC_USDT."""
    base = symbol.split(":")[0]
    return base.replace("/", "_").upper()


def canonical_symbol(symbol: str) -> str:
    return symbol.split(":")[0].upper()


def exchange_symbol(symbol: str, market_type: str) -> str:
    return mexc_contract_symbol(symbol) if market_type == "swap" else canonical_symbol(symbol).replace("/", "")


def dt_from_ms(ms: int | float | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(float(ms) / 1000, tz=UTC).isoformat()


@dataclass(frozen=True)
class BookDelta:
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    first_sequence: int | None
    final_sequence: int | None
    previous_sequence: int | None
    event_time_ms: int | None
    received_monotonic_ns: int
    replace_snapshot: bool = False


@dataclass(frozen=True)
class TapeDelta:
    trade_id: str
    price: float
    size: float
    side: str
    sequence: int | None
    event_time_ms: int | None
    received_monotonic_ns: int


class LocalOrderBook:
    def __init__(self, depth: int) -> None:
        self.depth = depth
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.sequence: int | None = None

    def load_snapshot(self, bids: list[list[float]], asks: list[list[float]], sequence: int | None) -> None:
        self.bids = {float(price): float(size) for price, size, *_ in bids if float(size) > 0}
        self.asks = {float(price): float(size) for price, size, *_ in asks if float(size) > 0}
        self.sequence = sequence
        self._trim()
        self.validate()

    def apply_delta(self, delta: BookDelta) -> None:
        if self.sequence is None:
            raise ValueError("orderbook snapshot is not loaded")
        if delta.previous_sequence is not None and delta.previous_sequence != self.sequence:
            raise ValueError(f"sequence gap: previous={delta.previous_sequence} local={self.sequence}")
        if delta.first_sequence is not None and delta.final_sequence is not None:
            if delta.final_sequence <= self.sequence:
                return
            if not (delta.first_sequence <= self.sequence + 1 <= delta.final_sequence):
                raise ValueError(f"sequence gap: first={delta.first_sequence} final={delta.final_sequence} local={self.sequence}")
        for level in delta.bids:
            self._set_level(self.bids, level)
        for level in delta.asks:
            self._set_level(self.asks, level)
        if delta.final_sequence is not None:
            self.sequence = delta.final_sequence
        self._trim()
        self.validate()

    def levels(self) -> tuple[list[OrderBookLevel], list[OrderBookLevel]]:
        bids = [OrderBookLevel(price, size) for price, size in sorted(self.bids.items(), reverse=True)[: self.depth]]
        asks = [OrderBookLevel(price, size) for price, size in sorted(self.asks.items())[: self.depth]]
        return bids, asks

    def validate(self) -> None:
        if not self.bids or not self.asks:
            raise ValueError("orderbook side is empty")
        bid_prices = sorted(self.bids.keys(), reverse=True)
        ask_prices = sorted(self.asks.keys())
        if any(price <= 0 or size <= 0 for price, size in [*self.bids.items(), *self.asks.items()]):
            raise ValueError("orderbook contains non-positive level")
        if bid_prices[0] >= ask_prices[0]:
            raise ValueError(f"crossed orderbook: bid={bid_prices[0]} ask={ask_prices[0]}")

    def _trim(self) -> None:
        self.bids = dict(sorted(self.bids.items(), reverse=True)[: self.depth])
        self.asks = dict(sorted(self.asks.items())[: self.depth])

    @staticmethod
    def _set_level(side: dict[float, float], level: OrderBookLevel) -> None:
        if level.price <= 0:
            raise ValueError("invalid price level")
        if level.size < 0:
            raise ValueError("negative depth level")
        if level.size == 0:
            side.pop(level.price, None)
        else:
            side[level.price] = level.size


class NativeFeedParser:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.exchange = config.exchange.name
        self.symbol = config.trading.symbol
        self.market_type = config.trading.market_type

    def url(self) -> str:
        stream_symbol = symbol_stream(self.symbol)
        if self.exchange == "binance":
            base = "wss://fstream.binance.com/stream" if self.market_type == "swap" else "wss://stream.binance.com:9443/stream"
            return f"{base}?streams={stream_symbol}@depth@100ms/{stream_symbol}@trade"
        if self.exchange == "bybit":
            channel = "linear" if self.market_type == "swap" else "spot"
            return f"wss://stream.bybit.com/v5/public/{channel}"
        if self.exchange == "mexc":
            if self.market_type == "swap":
                return "wss://contract.mexc.com/edge"
            return "wss://wbs.mexc.com/ws"
        raise ValueError(f"unsupported exchange websocket: {self.exchange}")

    def subscriptions(self) -> list[dict[str, Any]]:
        if self.exchange == "mexc" and self.market_type == "swap":
            symbol = exchange_symbol(self.symbol, self.market_type)
            return [
                {"method": "sub.depth", "param": {"symbol": symbol}},
                {"method": "sub.deal", "param": {"symbol": symbol}},
            ]
        if self.exchange == "mexc":
            symbol = exchange_symbol(self.symbol, self.market_type)
            return [
                {"method": "SUBSCRIPTION", "params": [f"spot@public.limit.depth.v3.api@{symbol}@20"]},
                {"method": "SUBSCRIPTION", "params": [f"spot@public.deals.v3.api@{symbol}"]},
            ]
        return []

    def parse(self, payload: dict[str, Any], received_ns: int) -> tuple[list[BookDelta], list[TapeDelta]]:
        if self.exchange == "mexc":
            if self.market_type == "swap":
                return self._parse_mexc_futures(payload, received_ns)
            return self._parse_mexc(payload, received_ns)
        return [], []

    def _parse_binance(self, payload: dict[str, Any], received_ns: int) -> tuple[list[BookDelta], list[TapeDelta]]:
        data = payload.get("data", payload)
        event_type = data.get("e")
        if event_type == "depthUpdate":
            return [
                BookDelta(
                    bids=[OrderBookLevel(float(price), float(size)) for price, size in data.get("b", [])],
                    asks=[OrderBookLevel(float(price), float(size)) for price, size in data.get("a", [])],
                    first_sequence=int(data["U"]),
                    final_sequence=int(data["u"]),
                    previous_sequence=int(data["pu"]) if data.get("pu") is not None else None,
                    event_time_ms=int(data["E"]) if data.get("E") else None,
                    received_monotonic_ns=received_ns,
                )
            ], []
        if event_type == "trade":
            side = "sell" if data.get("m") else "buy"
            trade_id = str(data.get("t"))
            return [], [
                TapeDelta(
                    trade_id=trade_id,
                    price=float(data.get("p") or 0),
                    size=float(data.get("q") or 0),
                    side=side,
                    sequence=int(data["t"]) if data.get("t") is not None else None,
                    event_time_ms=int(data["T"]) if data.get("T") else int(data["E"]) if data.get("E") else None,
                    received_monotonic_ns=received_ns,
                )
            ]
        return [], []

    def _parse_bybit(self, payload: dict[str, Any], received_ns: int) -> tuple[list[BookDelta], list[TapeDelta]]:
        topic = str(payload.get("topic") or "")
        data = payload.get("data")
        if topic.startswith("orderbook") and isinstance(data, dict):
            sequence = int(data.get("u") or data.get("seq") or 0)
            is_snapshot = payload.get("type") == "snapshot"
            return [
                BookDelta(
                    bids=[OrderBookLevel(float(price), float(size)) for price, size in data.get("b", [])],
                    asks=[OrderBookLevel(float(price), float(size)) for price, size in data.get("a", [])],
                    first_sequence=sequence,
                    final_sequence=sequence,
                    previous_sequence=None,
                    event_time_ms=int(payload["ts"]) if payload.get("ts") else None,
                    received_monotonic_ns=received_ns,
                    replace_snapshot=is_snapshot,
                )
            ], []
        if topic.startswith("publicTrade") and isinstance(data, list):
            trades = []
            for trade in data:
                side = str(trade.get("S") or "").lower()
                trades.append(
                    TapeDelta(
                        trade_id=str(trade.get("i") or trade.get("T")),
                        price=float(trade.get("p") or 0),
                        size=float(trade.get("v") or 0),
                        side="buy" if side == "buy" else "sell",
                        sequence=int(trade["T"]) if trade.get("T") else None,
                        event_time_ms=int(trade["T"]) if trade.get("T") else int(payload["ts"]) if payload.get("ts") else None,
                        received_monotonic_ns=received_ns,
                    )
                )
            return [], trades
        return [], []

    def _parse_mexc(self, payload: dict[str, Any], received_ns: int) -> tuple[list[BookDelta], list[TapeDelta]]:
        channel = str(payload.get("c") or payload.get("channel") or "")
        data = payload.get("d") or payload.get("data") or {}
        event_time = int(payload["t"]) if payload.get("t") else None
        if "depth" in channel and isinstance(data, dict):
            sequence = int(data.get("r") or data.get("toVersion") or data.get("version") or 0)
            return [
                BookDelta(
                    bids=[OrderBookLevel(float(price), float(size)) for price, size in data.get("bids", []) or data.get("b", [])],
                    asks=[OrderBookLevel(float(price), float(size)) for price, size in data.get("asks", []) or data.get("a", [])],
                    first_sequence=sequence,
                    final_sequence=sequence,
                    previous_sequence=None,
                    event_time_ms=event_time,
                    received_monotonic_ns=received_ns,
                    replace_snapshot=True,
                )
            ], []
        if "deals" in channel:
            deals = data.get("deals") if isinstance(data, dict) else []
            trades = []
            for trade in deals or []:
                trade_time = int(trade.get("t") or event_time or 0) or None
                side_raw = str(trade.get("S") or trade.get("side") or "").lower()
                trades.append(
                    TapeDelta(
                        trade_id=f"{trade_time}-{trade.get('p')}-{trade.get('v')}",
                        price=float(trade.get("p") or 0),
                        size=float(trade.get("v") or trade.get("q") or 0),
                        side="buy" if side_raw in {"1", "buy"} else "sell",
                        sequence=trade_time,
                        event_time_ms=trade_time,
                        received_monotonic_ns=received_ns,
                    )
                )
            return [], trades
        return [], []

    def _parse_mexc_futures(self, payload: dict[str, Any], received_ns: int) -> tuple[list[BookDelta], list[TapeDelta]]:
        channel = str(payload.get("channel") or "")
        event_time = int(payload["ts"]) if payload.get("ts") else None
        if channel == "push.depth":
            data = payload.get("data") or {}
            version = int(data.get("version") or 0)
            bids = self._mexc_futures_levels(data.get("bids") or [])
            asks = self._mexc_futures_levels(data.get("asks") or [])
            return [
                BookDelta(
                    bids=bids,
                    asks=asks,
                    first_sequence=version,
                    final_sequence=version,
                    previous_sequence=None,
                    event_time_ms=event_time,
                    received_monotonic_ns=received_ns,
                    replace_snapshot=True,
                )
            ], []
        if channel == "push.deal":
            trades = []
            for trade in payload.get("data") or []:
                trade_time = int(trade.get("t") or event_time or 0) or None
                side_flag = int(trade.get("T") or 0)
                trade_id = str(trade.get("i") or f"{trade_time}-{trade.get('p')}-{trade.get('v')}")
                trades.append(
                    TapeDelta(
                        trade_id=trade_id,
                        price=float(trade.get("p") or 0),
                        size=float(trade.get("v") or 0),
                        side="buy" if side_flag == 1 else "sell",
                        sequence=trade_time,
                        event_time_ms=trade_time,
                        received_monotonic_ns=received_ns,
                    )
                )
            return [], trades
        return [], []

    @staticmethod
    def _mexc_futures_levels(levels: list) -> list[OrderBookLevel]:
        parsed: list[OrderBookLevel] = []
        for level in levels:
            if not level:
                continue
            price = float(level[0])
            size = float(level[2] if len(level) > 2 else level[1])
            if size > 0:
                parsed.append(OrderBookLevel(price, size))
        return parsed


class MarketDataEngine:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._signature: tuple[str, str, str] | None = None
        self._lock = asyncio.Lock()
        self._book: LocalOrderBook | None = None
        self._trades: deque[TapePrint] = deque(maxlen=1000)
        self._seen_trade_ids: OrderedDict[str, None] = OrderedDict()
        self._last_trade_sequence: int | None = None
        self._status = "STOPPED"
        self._reason = "market data engine stopped"
        self._last_book_event_at: str | None = None
        self._last_trade_event_at: str | None = None
        self._last_book_monotonic_ns: int | None = None
        self._last_trade_monotonic_ns: int | None = None
        self._last_ws_monotonic_ns: int | None = None
        self._state = MarketState()
        self._book_subscribers: list[Callable[[dict[str, Any]], Awaitable[None] | None]] = []
        self._trade_subscribers: list[Callable[[dict[str, Any]], Awaitable[None] | None]] = []
        self._last_health_persist_ns: int | None = None
        self._dom_queue: deque[dict[str, Any]] = deque(maxlen=2000)
        self._tape_queue: deque[dict[str, Any]] = deque(maxlen=5000)
        self._latency_samples: deque[float] = deque(maxlen=500)
        self._dropped_ui_events = 0
        self._processed_ui_events = 0
        self._reconnect_count = 0
        self._reconnect_events: deque[float] = deque(maxlen=50)
        self._resync_count = 0
        self._desync_count = 0
        self._spot_last_sequence: int | None = None
        self._price_step: float | None = None
        self._size_step: float | None = None
        self._candles_1m: OrderedDict[int, dict[str, float | int]] = OrderedDict()

    def subscribe_orderbook_updates(self, callback: Callable[[dict[str, Any]], Awaitable[None] | None]) -> None:
        self._book_subscribers.append(callback)

    def subscribe_trade_updates(self, callback: Callable[[dict[str, Any]], Awaitable[None] | None]) -> None:
        self._trade_subscribers.append(callback)

    async def market_state(self, config: AppConfig) -> dict[str, Any]:
        await self.ensure_started(config)
        health = await self.health(config, persist=False)
        async with self._lock:
            payload = self._state.to_payload()
        payload["health"] = health
        return payload

    async def ensure_started(self, config: AppConfig) -> None:
        signature = (config.exchange.name, config.trading.market_type, config.trading.symbol)
        if self._task and not self._task.done() and self._signature == signature:
            return
        await self.stop()
        self._signature = signature
        self._task = asyncio.create_task(self._run(config))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        async with self._lock:
            self._status = "STOPPED"
            self._reason = "market data engine stopped"
            self._state.ws_status = self._status
            self._state.ws_reason = self._reason

    async def snapshot(self, config: AppConfig) -> tuple[MarketSnapshot | None, dict]:
        await self.ensure_started(config)
        health = await self.health(config)
        if health["status"] != "OK" or self._book is None:
            return None, health
        async with self._lock:
            bids, asks = self._book.levels()
            if not bids or not asks:
                return None, {**health, "status": "UNHEALTHY", "reason": "orderbook has no valid levels"}
            bid, ask = bids[0], asks[0]
            liquidity = sum(level.notional for level in bids[:5] + asks[:5])
            snapshot = MarketSnapshot(
                bid=bid.price,
                ask=ask.price,
                bid_size=bid.size,
                ask_size=ask.size,
                liquidity=liquidity,
                timestamp=self._last_book_event_at or datetime.now(UTC).isoformat(),
                bids=bids,
                asks=asks,
                recent_trades=list(self._trades),
            )
            return snapshot, health

    async def health(self, config: AppConfig, persist: bool = True) -> dict:
        now = monotonic_ns()
        async with self._lock:
            status = self._status
            reason = self._reason
            sequence = self._book.sequence if self._book else None
            if self._book is None or self._last_book_monotonic_ns is None:
                status, reason = "UNHEALTHY", "orderbook_not_ready"
            elif sequence is None:
                status, reason = "UNHEALTHY", "sequence_not_available"
            elif self._last_trade_monotonic_ns is None:
                status, reason = "UNHEALTHY", "tape_not_ready"
            elif self._last_ws_monotonic_ns and ns_to_ms(now - self._last_ws_monotonic_ns) > config.strategy.websocket_silence_seconds * 1000:
                status, reason = "UNHEALTHY", "websocket_silent"
            elif self._last_book_monotonic_ns and ns_to_ms(now - self._last_book_monotonic_ns) > config.strategy.market_data_stale_after_seconds * 1000:
                status, reason = "UNHEALTHY", "orderbook_stale"
            elif self._last_trade_monotonic_ns and ns_to_ms(now - self._last_trade_monotonic_ns) > config.strategy.tape_silence_seconds * 1000:
                status, reason = "UNHEALTHY", "tape_stale"
            payload = {
                "status": status,
                "reason": reason,
                "sequence": sequence,
                "last_book_event_at": self._last_book_event_at,
                "last_trade_event_at": self._last_trade_event_at,
                "measured_at_monotonic_ns": now,
                "dom_queue_depth": len(self._dom_queue),
                "tape_queue_depth": len(self._tape_queue),
                "desync_count": self._desync_count,
                "resync_count": self._resync_count,
                "reconnect_count": self._reconnect_count,
                "book_apply_latency_ms": self._state.book_apply_latency_ms,
                "tick_to_render_p95": self._p95(list(self._latency_samples)),
                "ui_drop_rate": (
                    self._dropped_ui_events / max(1, self._dropped_ui_events + self._processed_ui_events)
                ),
                "feed_state": self._state.feed_state,
                "clock_skew_ms": self._state.clock_skew_ms,
            }
        should_persist = False
        if persist:
            if self._last_health_persist_ns is None:
                should_persist = True
            elif ns_to_ms(now - self._last_health_persist_ns) >= 5000:
                should_persist = True
        if should_persist:
            self._last_health_persist_ns = now
            self._write_async(
                trade_repository.insert_market_data_health,
                config.exchange.name,
                config.trading.market_type,
                config.trading.symbol,
                payload["status"],
                payload["reason"],
                payload["sequence"],
                payload["last_book_event_at"],
                payload["last_trade_event_at"],
                payload["measured_at_monotonic_ns"],
            )
        return payload

    async def _run(self, config: AppConfig) -> None:
        parser = NativeFeedParser(config)
        allow_insecure_tls = False
        reconnect_attempt = 0
        while True:
            try:
                await self._mark("CONNECTING", "connecting websocket")
                await self._load_snapshot(config)
                ssl_context = self._build_ssl_context(allow_insecure_tls)
                async with websockets.connect(
                    parser.url(),
                    ping_interval=15,
                    ping_timeout=10,
                    max_queue=128,
                    ssl=ssl_context,
                ) as ws:
                    reconnect_attempt = 0
                    allow_insecure_tls = False
                    self._reconnect_count += 1
                    now_ts = time.time()
                    self._reconnect_events.append(now_ts)
                    reconnect_30s = [t for t in self._reconnect_events if now_ts - t <= 30.0]
                    if len(reconnect_30s) >= 3:
                        self._state.feed_state = "RECOVERING"
                    for subscription in parser.subscriptions():
                        await ws.send(json.dumps(subscription))
                    await self._mark("OK", "websocket synchronized")
                    async for raw in ws:
                        received_ns = monotonic_ns()
                        async with self._lock:
                            self._last_ws_monotonic_ns = received_ns
                        payload = json.loads(raw)
                        deltas, trades = parser.parse(payload, received_ns)
                        await self._apply_book_deltas(config, deltas)
                        await self._apply_trades(config, trades)
            except asyncio.CancelledError:
                raise
            except ssl.SSLCertVerificationError as exc:
                if allow_insecure_tls:
                    logger.exception("Market data websocket TLS verification failed in insecure fallback mode")
                    await self._mark("UNHEALTHY", f"websocket_error:{exc}")
                    await asyncio.sleep(1.0)
                    continue
                logger.warning(
                    "Market data TLS verification failed (%s). Falling back to insecure TLS for websocket feed.",
                    exc,
                )
                allow_insecure_tls = True
                await self._mark("UNHEALTHY", "websocket_tls_verification_failed_using_insecure_fallback")
                reconnect_attempt += 1
                await asyncio.sleep(min(5.0, 0.2 * (2**min(reconnect_attempt, 5))))
                continue
            except Exception as exc:
                logger.exception("Market data websocket failed")
                await self._mark("UNHEALTHY", f"websocket_error:{exc}")
                reconnect_attempt += 1
                await asyncio.sleep(min(8.0, 0.5 * (2**min(reconnect_attempt, 5))))

    @staticmethod
    def _build_ssl_context(insecure: bool) -> ssl.SSLContext:
        if insecure:
            return ssl._create_unverified_context()  # noqa: SLF001 - explicit fallback for intercepted TLS environments.
        return ssl.create_default_context()

    async def _load_snapshot(self, config: AppConfig) -> None:
        started = monotonic_ns()
        client = exchange_adapter._build_client(config)
        market_meta: dict[str, Any] = {}
        try:
            await asyncio.to_thread(client.load_markets)
            market_lookup = await asyncio.to_thread(client.market, config.trading.symbol)
            market_meta = market_lookup if isinstance(market_lookup, dict) else {}
        except Exception:
            market_meta = {}
        precision = market_meta.get("precision") if isinstance(market_meta, dict) else {}
        self._price_step = float(precision.get("price") or 0.0) if isinstance(precision, dict) else None
        self._size_step = float(precision.get("amount") or 0.0) if isinstance(precision, dict) else None
        book = await asyncio.to_thread(client.fetch_order_book, config.trading.symbol, limit=config.strategy.orderbook_depth_levels)
        sequence = int(book["nonce"]) if book.get("nonce") is not None else None
        local_book = LocalOrderBook(config.strategy.orderbook_depth_levels)
        local_book.load_snapshot(book.get("bids") or [], book.get("asks") or [], sequence)
        async with self._lock:
            self._book = local_book
            self._trades.clear()
            self._seen_trade_ids.clear()
            self._last_trade_sequence = None
            self._last_book_monotonic_ns = monotonic_ns()
            self._last_book_event_at = datetime.now(UTC).isoformat()
        self._latency(config, "orderbook_snapshot_latency_ms", ns_to_ms(monotonic_ns() - started))

    async def _apply_book_deltas(self, config: AppConfig, deltas: list[BookDelta]) -> None:
        ordered_deltas = sorted(deltas, key=lambda item: item.final_sequence or item.received_monotonic_ns)
        for delta in ordered_deltas:
            started = monotonic_ns()
            try:
                if config.trading.market_type == "spot" and delta.final_sequence is not None:
                    if self._spot_last_sequence is not None and delta.final_sequence <= self._spot_last_sequence:
                        continue
                    self._spot_last_sequence = delta.final_sequence
                normalized_bids = [self._normalize_level(level) for level in delta.bids]
                normalized_asks = [self._normalize_level(level) for level in delta.asks]
                removed_bids = [level.price for level in normalized_bids if level.size == 0]
                removed_asks = [level.price for level in normalized_asks if level.size == 0]
                async with self._lock:
                    if self._book is None:
                        raise ValueError("missing local book")
                    if delta.replace_snapshot:
                        self._book.load_snapshot(
                            [[level.price, level.size] for level in normalized_bids],
                            [[level.price, level.size] for level in normalized_asks],
                            delta.final_sequence,
                        )
                    else:
                        self._book.apply_delta(
                            BookDelta(
                                bids=normalized_bids,
                                asks=normalized_asks,
                                first_sequence=delta.first_sequence,
                                final_sequence=delta.final_sequence,
                                previous_sequence=delta.previous_sequence,
                                event_time_ms=delta.event_time_ms,
                                received_monotonic_ns=delta.received_monotonic_ns,
                                replace_snapshot=delta.replace_snapshot,
                            )
                        )
                    self._last_book_monotonic_ns = monotonic_ns()
                    self._last_book_event_at = dt_from_ms(delta.event_time_ms) or datetime.now(UTC).isoformat()
                    bids, asks = self._book.levels()
                    self._state.exchange = config.exchange.name
                    self._state.market_type = config.trading.market_type
                    self._state.symbol = config.trading.symbol
                    self._state.ws_status = self._status
                    self._state.ws_reason = self._reason
                    self._state.feed_state = "OK"
                    self._state.book_apply_latency_ms = ns_to_ms(monotonic_ns() - started)
                    self._state.dom_queue_depth = len(self._dom_queue)
                    self._state.tape_queue_depth = len(self._tape_queue)
                    self._state.resync_count = self._resync_count
                    self._state.desync_count = self._desync_count
                    self._state.reconnect_count = self._reconnect_count
                    self._state.update_from_book(bids, asks, list(self._trades), self._book.sequence)
                self._latency(config, "orderbook_processing_latency_ms", ns_to_ms(monotonic_ns() - started))
                if delta.event_time_ms:
                    delay_ms = max(0.0, datetime.now(UTC).timestamp() * 1000 - delta.event_time_ms)
                    self._state.clock_skew_ms = delay_ms
                    self._latency(config, "orderbook_event_delay_ms", delay_ms)
                    if delay_ms > config.strategy.max_event_delay_ms:
                        raise ValueError(f"orderbook event delay too high: {delay_ms:.2f}ms")
                dom_payload = DomDeltaPayload.model_validate(
                    {
                        "type": "dom_delta",
                        "symbol": mexc_contract_symbol(config.trading.symbol),
                        "market_type": config.trading.market_type,
                        "sequence": delta.final_sequence,
                        "ts_exchange": delta.event_time_ms,
                        "ts_local": int(time.time() * 1000),
                        "spread": self._state.spread,
                        "best_bid": self._state.best_bid,
                        "best_ask": self._state.best_ask,
                        "updated_bids": [[lvl.price, lvl.size] for lvl in normalized_bids if lvl.size > 0],
                        "updated_asks": [[lvl.price, lvl.size] for lvl in normalized_asks if lvl.size > 0],
                        "removed_bids": removed_bids,
                        "removed_asks": removed_asks,
                        "book_health": self._state.ws_status,
                    }
                ).model_dump()
                self._dom_queue.append(dom_payload)
                await self._notify_subscribers(
                    self._book_subscribers,
                    {"type": "orderbook_update", "state": self._state.to_payload(), "dom_delta": dom_payload},
                )
            except Exception as exc:
                self._desync_count += 1
                await self._mark("UNHEALTHY", f"orderbook_gap_or_invalid:{exc}")
                self._state.feed_state = "DESYNC"
                self._resync_count += 1
                await self._load_snapshot(config)
                raise

    async def _apply_trades(self, config: AppConfig, trades: list[TapeDelta]) -> None:
        ordered_trades = sorted(trades, key=lambda item: item.sequence or item.received_monotonic_ns)
        for trade in ordered_trades:
            if trade.price <= 0 or trade.size <= 0 or trade.side not in {"buy", "sell"}:
                await self._mark("UNHEALTHY", "invalid_trade_payload")
                raise ValueError("invalid trade payload")
            async with self._lock:
                if self._book is not None:
                    bids, asks = self._book.levels()
                    tolerance = config.strategy.trade_book_validation_tolerance_bps / 10_000
                    if bids and asks and (
                        (trade.side == "buy" and trade.price < bids[0].price * (1 - tolerance))
                        or (trade.side == "sell" and trade.price > asks[0].price * (1 + tolerance))
                    ):
                        self._status = "UNHEALTHY"
                        self._reason = "trade_aggressor_side_inconsistent_with_book"
                        raise ValueError("trade aggressor side inconsistent with book")
            if trade.trade_id in self._seen_trade_ids:
                continue
            if trade.sequence is not None and self._last_trade_sequence is not None and trade.sequence < self._last_trade_sequence:
                await self._mark("UNHEALTHY", "trade_order_regression")
                raise ValueError("trade order regression")
            event_at = dt_from_ms(trade.event_time_ms) or datetime.now(UTC).isoformat()
            async with self._lock:
                self._seen_trade_ids[trade.trade_id] = None
                self._seen_trade_ids.move_to_end(trade.trade_id)
                while len(self._seen_trade_ids) > 10_000:
                    self._seen_trade_ids.popitem(last=False)
                self._last_trade_sequence = trade.sequence if trade.sequence is not None else self._last_trade_sequence
                self._last_trade_monotonic_ns = monotonic_ns()
                self._last_trade_event_at = event_at
                new_trade = TapePrint(price=trade.price, size=trade.size, side=trade.side, timestamp=event_at)
                self._trades.append(new_trade)
                if self._book is not None:
                    bids, asks = self._book.levels()
                    self._state.exchange = config.exchange.name
                    self._state.market_type = config.trading.market_type
                    self._state.symbol = config.trading.symbol
                    self._state.ws_status = self._status
                    self._state.ws_reason = self._reason
                    self._state.update_from_book(bids, asks, list(self._trades), self._book.sequence)
            await self._notify_subscribers(
                self._trade_subscribers,
                {
                    "type": "trade_update",
                    "trade": {"price": trade.price, "size": trade.size, "side": trade.side, "timestamp": event_at},
                    "state": self._state.to_payload(),
                },
            )
            notional = trade.price * trade.size
            aggressor = "buyer" if trade.side == "buy" else "seller"
            tape_payload = TapeTradePayload.model_validate(
                {
                    "type": "tape_trade",
                    "symbol": mexc_contract_symbol(config.trading.symbol),
                    "market_type": config.trading.market_type,
                    "trade_id": trade.trade_id,
                    "side": trade.side,
                    "aggressor": aggressor,
                    "price": trade.price,
                    "size": trade.size,
                    "notional": notional,
                    "ts_exchange": trade.event_time_ms,
                    "ts_local": int(time.time() * 1000),
                }
            ).model_dump()
            before = len(self._tape_queue)
            self._tape_queue.append(tape_payload)
            if len(self._tape_queue) == self._tape_queue.maxlen and before == self._tape_queue.maxlen:
                self._dropped_ui_events += 1
            self._processed_ui_events += 1
            now_s = time.time()
            one_sec = [t for t in list(self._trades)[-200:] if (now_s - datetime.fromisoformat(t.timestamp.replace("Z", "+00:00")).timestamp()) <= 1.0]
            buy_notional = sum(t.price * t.size for t in one_sec if t.side == "buy")
            sell_notional = sum(t.price * t.size for t in one_sec if t.side == "sell")
            total = buy_notional + sell_notional
            self._state.buy_aggression_rate = buy_notional / total if total > 0 else 0.0
            self._state.sell_aggression_rate = sell_notional / total if total > 0 else 0.0
            self._state.delta_velocity = buy_notional - sell_notional
            self._state.tape_velocity_1s = sum(t.size for t in one_sec)
            self._update_candles_1m(trade)
            self._state.candles_1m = list(self._candles_1m.values())[-300:]
            await self._notify_subscribers(
                self._trade_subscribers,
                {"type": "trade_payload", "tape_trade": tape_payload, "state": self._state.to_payload()},
            )
            if trade.event_time_ms:
                delay_ms = max(0.0, datetime.now(UTC).timestamp() * 1000 - trade.event_time_ms)
                self._latency_samples.append(delay_ms)
                self._latency(config, "trade_event_delay_ms", delay_ms)
                if delay_ms > config.strategy.max_event_delay_ms:
                    await self._mark("UNHEALTHY", f"trade event delay too high: {delay_ms:.2f}ms")
                    raise ValueError("trade event delay too high")

    async def _mark(self, status: str, reason: str) -> None:
        async with self._lock:
            self._status = status
            self._reason = reason
            self._state.ws_status = status
            self._state.ws_reason = reason
            if status == "OK":
                self._state.feed_state = "OK"
            elif "stale" in reason or "silent" in reason:
                self._state.feed_state = "DELAYED"
            elif "gap" in reason or "invalid" in reason:
                self._state.feed_state = "DESYNC"
            else:
                self._state.feed_state = "RECOVERING"

    @staticmethod
    def _latency(config: AppConfig, metric: str, value_ms: float) -> None:
        # Keep hot path in-memory only for MVP realtime responsiveness.
        _ = (config, metric, value_ms)

    @staticmethod
    def _write_async(func: Any, *args: Any) -> None:
        try:
            asyncio.get_running_loop().create_task(asyncio.to_thread(func, *args))
        except RuntimeError:
            func(*args)

    def _normalize_level(self, level: OrderBookLevel) -> OrderBookLevel:
        price = level.price
        size = level.size
        if self._price_step and self._price_step > 0:
            price = round(round(price / self._price_step) * self._price_step, 12)
        if self._size_step and self._size_step > 0:
            size = round(round(size / self._size_step) * self._size_step, 12)
        return OrderBookLevel(price=price, size=size)

    def _update_candles_1m(self, trade: TapeDelta) -> None:
        ts_ms = int(trade.event_time_ms or int(time.time() * 1000))
        bucket = (ts_ms // 60000) * 60000
        candle = self._candles_1m.get(bucket)
        if candle is None:
            self._candles_1m[bucket] = {
                "ts": bucket,
                "open": trade.price,
                "high": trade.price,
                "low": trade.price,
                "close": trade.price,
                "volume": trade.size,
            }
        else:
            candle["high"] = max(float(candle["high"]), trade.price)
            candle["low"] = min(float(candle["low"]), trade.price)
            candle["close"] = trade.price
            candle["volume"] = float(candle["volume"]) + trade.size
        while len(self._candles_1m) > 600:
            self._candles_1m.popitem(last=False)

    @staticmethod
    def _p95(values: list[float]) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = int(max(0, min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))))
        return ordered[idx]

    @staticmethod
    async def _notify_subscribers(
        subscribers: list[Callable[[dict[str, Any]], Awaitable[None] | None]],
        payload: dict[str, Any],
    ) -> None:
        for callback in subscribers:
            try:
                result = callback(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # pragma: no cover - subscriber failure should not break feed
                logger.exception("MarketData subscriber failed")


market_data_engine = MarketDataEngine()
