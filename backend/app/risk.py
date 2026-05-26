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
        self._cooldown_until: datetime | None = None

    def _load_inventory(self) -> float:
        trades = self.repository.list_trades(limit=5000)
        return sum(float(trade["size"]) if trade["side"] == "buy" else -float(trade["size"]) for trade in trades)

    def check(self, config: AppConfig, side: str, price: float, size: float) -> RiskDecision:
        now = datetime.now(UTC)
        if self._cooldown_until and now < self._cooldown_until:
            return RiskDecision(False, "cooldown_after_loss", self._cooldown_until.isoformat())
        if self.repository.daily_pnl(now) <= -config.risk.max_daily_loss:
            return RiskDecision(False, "max_daily_loss_exceeded")
        if size > config.risk.max_position_size:
            return RiskDecision(False, "max_position_size_exceeded")
        signed_size = size if side == "buy" else -size
        if abs((self.inventory + signed_size) * price) > config.risk.max_inventory_exposure:
            return RiskDecision(False, "max_inventory_exposure_exceeded")
        return RiskDecision(True, "risk_allowed")

    def record_fill(self, side: str, size: float, pnl: float, config: AppConfig) -> None:
        self.inventory += size if side == "buy" else -size
        if pnl < 0 and config.risk.cooldown_after_loss_seconds > 0:
            self._cooldown_until = datetime.now(UTC) + timedelta(seconds=config.risk.cooldown_after_loss_seconds)

    def status(self) -> dict:
        return {"inventory": self.inventory, "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None}
