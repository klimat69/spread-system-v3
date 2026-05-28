from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .strategy import OrderBookLevel, TapePrint


@dataclass(slots=True)
class MarketState:
    exchange: str = "mexc"
    market_type: str = "swap"
    symbol: str = "BTC/USDT"
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread: float = 0.0
    imbalance: float = 0.0
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)
    recent_trades: list[TapePrint] = field(default_factory=list)
    ws_status: str = "STOPPED"
    ws_reason: str = "market data engine stopped"
    feed_state: str = "RECOVERING"
    last_update: str | None = None
    sequence: int | None = None
    clock_skew_ms: float = 0.0
    tape_velocity_1s: float = 0.0
    buy_aggression_rate: float = 0.0
    sell_aggression_rate: float = 0.0
    delta_velocity: float = 0.0
    dom_queue_depth: int = 0
    tape_queue_depth: int = 0
    resync_count: int = 0
    desync_count: int = 0
    reconnect_count: int = 0
    ui_drop_rate: float = 0.0
    book_apply_latency_ms: float = 0.0
    candles_1m: list[dict[str, float | int]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "market_type": self.market_type,
            "symbol": self.symbol,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "spread": self.spread,
            "imbalance": self.imbalance,
            "bids": [{"price": level.price, "size": level.size} for level in self.bids],
            "asks": [{"price": level.price, "size": level.size} for level in self.asks],
            "recent_trades": [
                {"price": trade.price, "size": trade.size, "side": trade.side, "timestamp": trade.timestamp}
                for trade in self.recent_trades
            ],
            "ws_status": self.ws_status,
            "ws_reason": self.ws_reason,
            "feed_state": self.feed_state,
            "last_update": self.last_update,
            "sequence": self.sequence,
            "clock_skew_ms": self.clock_skew_ms,
            "tape_velocity_1s": self.tape_velocity_1s,
            "buy_aggression_rate": self.buy_aggression_rate,
            "sell_aggression_rate": self.sell_aggression_rate,
            "delta_velocity": self.delta_velocity,
            "dom_queue_depth": self.dom_queue_depth,
            "tape_queue_depth": self.tape_queue_depth,
            "resync_count": self.resync_count,
            "desync_count": self.desync_count,
            "reconnect_count": self.reconnect_count,
            "ui_drop_rate": self.ui_drop_rate,
            "book_apply_latency_ms": self.book_apply_latency_ms,
            "candles_1m": self.candles_1m,
        }

    def update_from_book(
        self,
        bids: list[OrderBookLevel],
        asks: list[OrderBookLevel],
        recent_trades: list[TapePrint],
        sequence: int | None,
    ) -> None:
        self.bids = bids
        self.asks = asks
        self.recent_trades = recent_trades[-200:]
        self.sequence = sequence
        self.last_update = datetime.now(UTC).isoformat()
        if bids and asks:
            self.best_bid = bids[0].price
            self.best_ask = asks[0].price
            mid = (self.best_bid + self.best_ask) / 2 if self.best_bid > 0 and self.best_ask > 0 else 0.0
            self.spread = (self.best_ask - self.best_bid) / mid if mid > 0 else 0.0
            bid_pressure = sum(level.price * level.size for level in bids[:10])
            ask_pressure = sum(level.price * level.size for level in asks[:10])
            total_pressure = bid_pressure + ask_pressure
            self.imbalance = (bid_pressure - ask_pressure) / total_pressure if total_pressure > 0 else 0.0
        else:
            self.best_bid = 0.0
            self.best_ask = 0.0
            self.spread = 0.0
            self.imbalance = 0.0
