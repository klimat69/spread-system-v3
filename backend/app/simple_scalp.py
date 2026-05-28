from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from .config import AppConfig
from .market_state import MarketState


Signal = Literal["buy", "sell", "flat"]


@dataclass(slots=True)
class ScalpDecision:
    signal: Signal
    should_enter: bool
    should_exit: bool
    reason: str


class SimpleScalpEngine:
    """Lightweight event-driven micro scalping logic for MVP."""

    def __init__(self) -> None:
        self._last_signal: Signal = "flat"
        self._last_eval_at: str | None = None

    def evaluate(self, state: MarketState, config: AppConfig) -> ScalpDecision:
        tape = state.recent_trades[-60:]
        buy_notional = sum(t.price * t.size for t in tape if t.side == "buy")
        sell_notional = sum(t.price * t.size for t in tape if t.side == "sell")
        total_notional = buy_notional + sell_notional
        aggression = (buy_notional - sell_notional) / total_notional if total_notional > 0 else 0.0

        spread_ok = state.spread >= config.simple_scalp.spread_min
        imbalance_ok = abs(state.imbalance) >= config.simple_scalp.imbalance_min
        aggression_ok = abs(aggression) >= config.simple_scalp.aggression_min

        next_signal: Signal = "flat"
        if spread_ok and imbalance_ok and aggression_ok:
            if state.imbalance > 0 and aggression > 0:
                next_signal = "buy"
            elif state.imbalance < 0 and aggression < 0:
                next_signal = "sell"

        should_enter = self._last_signal == "flat" and next_signal in {"buy", "sell"}
        should_exit = self._last_signal in {"buy", "sell"} and (
            next_signal == "flat" or (next_signal in {"buy", "sell"} and next_signal != self._last_signal)
        )

        if should_enter:
            self._last_signal = next_signal
            reason = f"entry_{next_signal}"
        elif should_exit:
            prev_signal = self._last_signal
            self._last_signal = "flat"
            reason = f"exit_{prev_signal}"
        else:
            reason = "hold" if self._last_signal != "flat" else "no_signal"

        self._last_eval_at = datetime.now(UTC).isoformat()
        return ScalpDecision(signal=self._last_signal, should_enter=should_enter, should_exit=should_exit, reason=reason)

    @property
    def last_eval_at(self) -> str | None:
        return self._last_eval_at
