from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import pstdev

from .config import AppConfig


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    size: float

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass(frozen=True)
class TapePrint:
    price: float
    size: float
    side: str
    timestamp: str

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass(frozen=True)
class LiquidityWall:
    side: str
    price: float
    size: float
    notional: float
    distance_bps: float
    strength: float


@dataclass(frozen=True)
class TapeAnalysis:
    aggressive_buy_notional: float
    aggressive_sell_notional: float
    net_aggression: float
    total_notional: float
    burst_ratio: float

    @property
    def direction(self) -> str:
        if self.net_aggression > 0:
            return "buy"
        if self.net_aggression < 0:
            return "sell"
        return "neutral"


@dataclass(frozen=True)
class MarketSnapshot:
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    liquidity: float
    timestamp: str
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)
    recent_trades: list[TapePrint] = field(default_factory=list)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return (self.ask - self.bid) / self.mid if self.mid > 0 else 0.0

    @property
    def imbalance(self) -> float:
        bid_pressure = self.bid_pressure
        ask_pressure = self.ask_pressure
        total = bid_pressure + ask_pressure
        return (bid_pressure - ask_pressure) / total if total > 0 else 0.0

    @property
    def bid_pressure(self) -> float:
        levels = self.bids or [OrderBookLevel(self.bid, self.bid_size)]
        return self._weighted_depth(levels, self.bid)

    @property
    def ask_pressure(self) -> float:
        levels = self.asks or [OrderBookLevel(self.ask, self.ask_size)]
        return self._weighted_depth(levels, self.ask)

    @staticmethod
    def _weighted_depth(levels: list[OrderBookLevel], best_price: float) -> float:
        pressure = 0.0
        for idx, level in enumerate(levels):
            distance = abs(level.price - best_price) / best_price if best_price > 0 else 0.0
            level_weight = 1 / (idx + 1)
            distance_weight = max(0.1, 1 - distance * 100)
            pressure += level.notional * level_weight * distance_weight
        return pressure


@dataclass(frozen=True)
class StrategyDecision:
    should_trade: bool
    should_exit: bool
    reason: str
    side: str
    spread: float
    edge: float
    volatility: float
    imbalance: float
    liquidity: float
    executable: bool
    bid_pressure: float
    ask_pressure: float
    tape_aggression: float
    tape_buy_notional: float
    tape_sell_notional: float
    tape_burst_ratio: float
    micro_trend: str
    entry_reason: str | None
    exit_reason: str | None
    expected_holding_seconds: float
    liquidity_walls: list[dict]


class StrategyEngine:
    def __init__(self) -> None:
        self._mid_prices: list[float] = []
        self._baseline_tape_notional: float | None = None
        self._last_support_wall_side: str | None = None

    def evaluate(self, snapshot: MarketSnapshot, config: AppConfig) -> StrategyDecision:
        self._mid_prices.append(snapshot.mid)
        self._mid_prices = self._mid_prices[-config.strategy.volatility_window:]
        volatility = self._volatility()
        walls = self.detect_liquidity_walls(snapshot, config)
        tape = self.analyze_tape(snapshot, config)
        micro_trend = self._micro_trend(snapshot.imbalance, tape.net_aggression, walls)
        exit_reason = self._exit_reason(snapshot, config, tape, micro_trend, walls)
        entry_reason: str | None = None
        side = "buy"
        if snapshot.bid <= 0 or snapshot.ask <= 0 or snapshot.ask <= snapshot.bid:
            return self._decision(False, False, "invalid_order_book", side, snapshot, volatility, tape, micro_trend, entry_reason, exit_reason, walls, config)
        if self._snapshot_age(snapshot) > config.strategy.max_orderbook_age_seconds:
            return self._decision(False, False, "stale_order_book", side, snapshot, volatility, tape, micro_trend, entry_reason, exit_reason, walls, config)
        if volatility >= config.strategy.volatility_threshold:
            return self._decision(False, bool(exit_reason), "volatility_too_high", side, snapshot, volatility, tape, micro_trend, entry_reason, exit_reason, walls, config)
        if snapshot.liquidity < config.strategy.min_liquidity:
            return self._decision(False, bool(exit_reason), "liquidity_insufficient", side, snapshot, volatility, tape, micro_trend, entry_reason, exit_reason, walls, config)
        if tape.total_notional < config.strategy.min_tape_notional:
            return self._decision(False, bool(exit_reason), "tape_insufficient", side, snapshot, volatility, tape, micro_trend, entry_reason, exit_reason, walls, config)

        has_bid_wall = any(wall.side == "bid" for wall in walls)
        has_ask_wall = any(wall.side == "ask" for wall in walls)
        strong_bid_pressure = snapshot.imbalance >= config.strategy.imbalance_limit
        strong_ask_pressure = snapshot.imbalance <= -config.strategy.imbalance_limit
        buy_aggression = tape.net_aggression >= config.strategy.tape_aggression_entry_threshold
        sell_aggression = tape.net_aggression <= -config.strategy.tape_aggression_entry_threshold
        burst = tape.burst_ratio >= config.strategy.momentum_burst_multiplier

        if strong_bid_pressure and buy_aggression and burst and not has_ask_wall:
            side = "buy"
            entry_reason = "bid_pressure_buy_aggression_momentum"
        elif strong_ask_pressure and sell_aggression and burst and not has_bid_wall:
            side = "sell"
            entry_reason = "ask_pressure_sell_aggression_momentum"
        else:
            reason = "orderflow_not_aligned"
            if has_ask_wall and strong_bid_pressure:
                reason = "resistance_wall_blocks_long"
            elif has_bid_wall and strong_ask_pressure:
                reason = "support_wall_blocks_short"
            return self._decision(False, bool(exit_reason), reason, side, snapshot, volatility, tape, micro_trend, entry_reason, exit_reason, walls, config)

        self._last_support_wall_side = "bid" if side == "buy" and has_bid_wall else "ask" if side == "sell" and has_ask_wall else None
        return self._decision(True, bool(exit_reason), entry_reason, side, snapshot, volatility, tape, micro_trend, entry_reason, exit_reason, walls, config)

    def analyze_tape(self, snapshot: MarketSnapshot, config: AppConfig) -> TapeAnalysis:
        cutoff = datetime.now(UTC).timestamp() - config.strategy.tape_window_seconds
        buy_notional = 0.0
        sell_notional = 0.0
        for trade in snapshot.recent_trades:
            try:
                timestamp = datetime.fromisoformat(trade.timestamp.replace("Z", "+00:00"))
            except ValueError:
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            if timestamp.timestamp() < cutoff:
                continue
            if trade.side == "buy":
                buy_notional += trade.notional
            elif trade.side == "sell":
                sell_notional += trade.notional
        total = buy_notional + sell_notional
        net = (buy_notional - sell_notional) / total if total > 0 else 0.0
        if self._baseline_tape_notional is None:
            self._baseline_tape_notional = total
        else:
            self._baseline_tape_notional = (self._baseline_tape_notional * 0.8) + (total * 0.2)
        baseline = self._baseline_tape_notional or total or 1.0
        burst_ratio = total / baseline if baseline > 0 else 0.0
        return TapeAnalysis(buy_notional, sell_notional, net, total, burst_ratio)

    def detect_liquidity_walls(self, snapshot: MarketSnapshot, config: AppConfig) -> list[LiquidityWall]:
        walls: list[LiquidityWall] = []
        mid = snapshot.mid
        for side, levels in (("bid", snapshot.bids), ("ask", snapshot.asks)):
            if not levels:
                continue
            avg_notional = sum(level.notional for level in levels) / len(levels)
            for level in levels:
                distance_bps = abs(level.price - mid) / mid * 10_000 if mid > 0 else float("inf")
                strength = level.notional / avg_notional if avg_notional > 0 else 0.0
                if distance_bps <= config.strategy.wall_proximity_bps and strength >= config.strategy.wall_multiplier and level.notional >= config.strategy.min_wall_notional:
                    walls.append(LiquidityWall(side, level.price, level.size, level.notional, distance_bps, strength))
        return sorted(walls, key=lambda wall: wall.strength, reverse=True)

    def _exit_reason(self, snapshot: MarketSnapshot, config: AppConfig, tape: TapeAnalysis, micro_trend: str, walls: list[LiquidityWall]) -> str | None:
        if abs(snapshot.imbalance) < config.strategy.imbalance_exit_threshold:
            return "imbalance_weakening"
        if abs(tape.net_aggression) < config.strategy.tape_aggression_exit_threshold:
            return "tape_aggression_faded"
        if micro_trend == "bullish" and tape.net_aggression < -config.strategy.tape_aggression_exit_threshold:
            return "opposite_sell_aggression"
        if micro_trend == "bearish" and tape.net_aggression > config.strategy.tape_aggression_exit_threshold:
            return "opposite_buy_aggression"
        wall_sides = {wall.side for wall in walls}
        if self._last_support_wall_side and self._last_support_wall_side not in wall_sides:
            removed = self._last_support_wall_side
            self._last_support_wall_side = None
            return f"{removed}_liquidity_wall_removed"
        return None

    @staticmethod
    def _micro_trend(imbalance: float, tape_aggression: float, walls: list[LiquidityWall]) -> str:
        wall_sides = {wall.side for wall in walls}
        if imbalance > 0 and tape_aggression > 0 and "ask" not in wall_sides:
            return "bullish"
        if imbalance < 0 and tape_aggression < 0 and "bid" not in wall_sides:
            return "bearish"
        if "bid" in wall_sides and "ask" not in wall_sides:
            return "supported"
        if "ask" in wall_sides and "bid" not in wall_sides:
            return "resisted"
        return "neutral"

    def _volatility(self) -> float:
        if len(self._mid_prices) < 2:
            return 0.0
        mean_price = sum(self._mid_prices) / len(self._mid_prices)
        return pstdev(self._mid_prices) / mean_price if mean_price > 0 else 0.0

    @staticmethod
    def _decision(
        should_trade: bool,
        should_exit: bool,
        reason: str,
        side: str,
        snapshot: MarketSnapshot,
        volatility: float,
        tape: TapeAnalysis,
        micro_trend: str,
        entry_reason: str | None,
        exit_reason: str | None,
        walls: list[LiquidityWall],
        config: AppConfig,
    ) -> StrategyDecision:
        return StrategyDecision(
            should_trade=should_trade,
            should_exit=should_exit,
            reason=reason,
            side=side,
            spread=snapshot.spread,
            edge=0.0,
            volatility=volatility,
            imbalance=snapshot.imbalance,
            liquidity=snapshot.liquidity,
            executable=should_trade,
            bid_pressure=snapshot.bid_pressure,
            ask_pressure=snapshot.ask_pressure,
            tape_aggression=tape.net_aggression,
            tape_buy_notional=tape.aggressive_buy_notional,
            tape_sell_notional=tape.aggressive_sell_notional,
            tape_burst_ratio=tape.burst_ratio,
            micro_trend=micro_trend,
            entry_reason=entry_reason,
            exit_reason=exit_reason,
            expected_holding_seconds=config.strategy.max_holding_seconds,
            liquidity_walls=[wall.__dict__ for wall in walls],
        )

    @staticmethod
    def _snapshot_age(snapshot: MarketSnapshot) -> float:
        try:
            timestamp = datetime.fromisoformat(snapshot.timestamp.replace("Z", "+00:00"))
        except ValueError:
            return float("inf")
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return (datetime.now(UTC) - timestamp).total_seconds()
