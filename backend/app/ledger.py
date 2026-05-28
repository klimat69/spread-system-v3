from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .config import AppConfig
from .database import Position, TradeRepository


@dataclass(frozen=True)
class LedgerResult:
    position: dict
    pnl: dict
    unreconciled: bool


def split_symbol(symbol: str) -> tuple[str, str]:
    if "/" not in symbol:
        return symbol, ""
    base, quote = symbol.split("/", 1)
    return base, quote.split(":")[0]


class PositionLedger:
    def __init__(self, repository: TradeRepository) -> None:
        self.repository = repository

    def rebuild_from_fills(self, config: AppConfig, mark_price: float | None = None) -> LedgerResult:
        fills = self.repository.list_fills(symbol=config.trading.symbol, limit=10000)
        if config.trading.market_type == "swap":
            return self._rebuild_swap(config, fills, mark_price)
        return self._rebuild_spot(config, fills, mark_price)

    def _rebuild_spot(self, config: AppConfig, fills: list[dict], mark_price: float | None) -> LedgerResult:
        base, quote = split_symbol(config.trading.symbol)
        size = 0.0
        avg_entry = 0.0
        realized = 0.0
        fees = 0.0
        unreconciled = False

        for fill in fills:
            fill_size = float(fill["size"])
            price = float(fill["price"])
            fees += float(fill["fee"])
            if fill["side"] == "buy":
                new_size = size + fill_size
                avg_entry = ((size * avg_entry) + (fill_size * price)) / new_size if new_size else 0.0
                size = new_size
            elif fill["side"] == "sell":
                if size <= 0:
                    unreconciled = True
                    realized += fill_size * price
                    size -= fill_size
                    avg_entry = price
                else:
                    closing = min(size, fill_size)
                    realized += (price - avg_entry) * closing
                    size -= closing
                    if fill_size > closing:
                        unreconciled = True
                        size -= fill_size - closing
                        avg_entry = price
                    elif size == 0:
                        avg_entry = 0.0

        mark = mark_price if mark_price is not None else avg_entry
        unrealized = (mark - avg_entry) * size if size and avg_entry else 0.0
        position = Position(
            exchange=config.exchange.name,
            market_type=config.trading.market_type,
            symbol=config.trading.symbol,
            base_asset=base,
            quote_asset=quote,
            size=size,
            average_entry_price=avg_entry,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            mark_price=mark or 0.0,
            source="ledger",
            last_synced_at=datetime.now(UTC).isoformat(),
        )
        stored_position = self.repository.upsert_position(position)
        pnl = self._insert_pnl_and_update_cooldown(config, realized, unrealized, fees, "fills")
        return LedgerResult(stored_position, pnl, unreconciled)

    def _rebuild_swap(self, config: AppConfig, fills: list[dict], mark_price: float | None) -> LedgerResult:
        # Local swap ledger is only a cross-check. Exchange positions remain the source of truth.
        base, quote = split_symbol(config.trading.symbol)
        signed = 0.0
        avg_entry = 0.0
        fees = 0.0
        for fill in fills:
            size = float(fill["size"])
            price = float(fill["price"])
            fees += float(fill["fee"])
            signed_fill = size if fill["side"] == "buy" else -size
            if signed == 0 or (signed > 0 and signed_fill > 0) or (signed < 0 and signed_fill < 0):
                new_abs = abs(signed) + abs(signed_fill)
                avg_entry = ((abs(signed) * avg_entry) + (abs(signed_fill) * price)) / new_abs if new_abs else 0.0
                signed += signed_fill
            else:
                if abs(signed_fill) > abs(signed):
                    signed = signed + signed_fill
                    avg_entry = price
                else:
                    signed = signed + signed_fill
                    if signed == 0:
                        avg_entry = 0.0
        mark = mark_price if mark_price is not None else avg_entry
        position = Position(
            exchange=config.exchange.name,
            market_type=config.trading.market_type,
            symbol=config.trading.symbol,
            base_asset=base,
            quote_asset=quote,
            size=signed,
            average_entry_price=avg_entry,
            realized_pnl=0.0,
            unrealized_pnl=(mark - avg_entry) * signed if signed else 0.0,
            mark_price=mark or 0.0,
            source="ledger-cross-check",
            last_synced_at=datetime.now(UTC).isoformat(),
        )
        stored_position = self.repository.upsert_position(position)
        pnl = self._insert_pnl_and_update_cooldown(config, 0.0, position.unrealized_pnl, fees, "fills-cross-check")
        return LedgerResult(stored_position, pnl, False)

    def _insert_pnl_and_update_cooldown(self, config: AppConfig, realized: float, unrealized: float, fees: float, source: str) -> dict:
        previous = self.repository.latest_pnl_snapshot(config.trading.symbol)
        pnl = self.repository.insert_pnl_snapshot(
            exchange=config.exchange.name,
            market_type=config.trading.market_type,
            symbol=config.trading.symbol,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            fees=fees,
            source=source,
        )
        previous_realized = float(previous.get("realized_pnl") or 0.0)
        realized_delta = realized - previous_realized
        if realized_delta < 0 and config.risk.cooldown_after_loss_seconds > 0:
            cooldown = datetime.now(UTC) + timedelta(seconds=config.risk.cooldown_after_loss_seconds)
            self.repository.update_risk_state(cooldown.isoformat(), datetime.now(UTC).isoformat())
        return pnl
