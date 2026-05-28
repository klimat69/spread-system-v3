from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .config import AppConfig
from .database import TradeRepository


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    cooldown_until: str | None = None


class RiskEngine:
    def __init__(self, repository: TradeRepository):
        self.repository = repository
        self.inventory = self._load_inventory()

    def check(self, config: AppConfig, side: str, price: float, size: float) -> RiskDecision:
        now = datetime.now(UTC)
        reconciliation = self.repository.reconciliation_status()
        if reconciliation["blocking"]:
            return RiskDecision(False, "reconciliation_blocked")
        state = self.repository.get_risk_state()
        cooldown_until = self._parse_time(state.get("cooldown_until"))
        if cooldown_until and now < cooldown_until:
            return RiskDecision(False, "cooldown_after_loss", cooldown_until.isoformat())
        if self.repository.daily_pnl(now) <= -config.risk.max_daily_loss:
            return RiskDecision(False, "max_daily_loss_exceeded")
        if size > config.risk.max_position_size:
            return RiskDecision(False, "max_position_size_exceeded")
        signed_size = size if side == "buy" else -size
        current_position = self._current_position(config)
        if abs((current_position + signed_size) * price) > config.risk.max_inventory_exposure:
            return RiskDecision(False, "max_inventory_exposure_exceeded")
        return RiskDecision(True, "risk_allowed")

    def record_fill(self, side: str, size: float, pnl: float, config: AppConfig) -> None:
        self.inventory += size if side == "buy" else -size
        if pnl < 0 and config.risk.cooldown_after_loss_seconds > 0:
            cooldown = datetime.now(UTC) + timedelta(seconds=config.risk.cooldown_after_loss_seconds)
            self.repository.update_risk_state(cooldown.isoformat(), datetime.now(UTC).isoformat())

    def status(self) -> dict:
        state = self.repository.get_risk_state()
        return {
            "inventory": self.inventory,
            "cooldown_until": state.get("cooldown_until"),
            "reconciliation": self.repository.reconciliation_status(),
        }

    def _load_inventory(self) -> float:
        positions = self.repository.list_positions()
        return sum(float(position["size"]) for position in positions)

    def _current_position(self, config: AppConfig) -> float:
        positions = self.repository.list_positions(symbol=config.trading.symbol)
        if not positions:
            return 0.0
        return float(positions[0]["size"])

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
