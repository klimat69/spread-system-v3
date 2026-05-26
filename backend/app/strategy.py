from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev

from .config import AppConfig


@dataclass(frozen=True)
class MarketSnapshot:
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    liquidity: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return (self.ask - self.bid) / self.mid if self.mid > 0 else 0.0

    @property
    def imbalance(self) -> float:
        total = self.bid_size + self.ask_size
        return (self.bid_size - self.ask_size) / total if total > 0 else 0.0


@dataclass(frozen=True)
class StrategyDecision:
    should_trade: bool
    reason: str
    side: str
    spread: float
    edge: float
    volatility: float
    imbalance: float
    liquidity: float


class StrategyEngine:
    def __init__(self) -> None:
        self._mid_prices: list[float] = []

    def evaluate(self, snapshot: MarketSnapshot, config: AppConfig) -> StrategyDecision:
        self._mid_prices.append(snapshot.mid)
        self._mid_prices = self._mid_prices[-config.strategy.volatility_window:]
        volatility = self._volatility()
        edge = snapshot.spread - (config.fees.maker + config.fees.taker)
        if snapshot.bid <= 0 or snapshot.ask <= 0 or snapshot.ask <= snapshot.bid:
            return self._decision(False, "invalid_order_book", "buy", snapshot, edge, volatility)
        if edge <= config.strategy.min_edge:
            return self._decision(False, "edge_below_minimum", "buy", snapshot, edge, volatility)
        if volatility >= config.strategy.volatility_threshold:
            return self._decision(False, "volatility_too_high", "buy", snapshot, edge, volatility)
        if abs(snapshot.imbalance) >= config.strategy.imbalance_limit:
            return self._decision(False, "imbalance_extreme", "buy", snapshot, edge, volatility)
        if snapshot.liquidity < config.strategy.min_liquidity:
            return self._decision(False, "liquidity_insufficient", "buy", snapshot, edge, volatility)
        side = "sell" if snapshot.imbalance > 0 else "buy"
        return self._decision(True, "trade_allowed", side, snapshot, edge, volatility)

    def _volatility(self) -> float:
        if len(self._mid_prices) < 2:
            return 0.0
        mean_price = sum(self._mid_prices) / len(self._mid_prices)
        return pstdev(self._mid_prices) / mean_price if mean_price > 0 else 0.0

    @staticmethod
    def _decision(should_trade: bool, reason: str, side: str, snapshot: MarketSnapshot, edge: float, volatility: float) -> StrategyDecision:
        return StrategyDecision(should_trade, reason, side, snapshot.spread, edge, volatility, snapshot.imbalance, snapshot.liquidity)
