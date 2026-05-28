from __future__ import annotations

from datetime import UTC, datetime
from datetime import timedelta

from .config import AppConfig
from .database import Position, ReconciliationEvent, TradeRepository, encode_raw
from .exchange import ExchangeAdapter, ExchangeOrder
from .ledger import PositionLedger, split_symbol

TERMINAL = {"FILLED", "CANCELLED", "REJECTED"}
ACTIVE = ["NEW", "SENT", "OPEN", "PARTIAL", "UNKNOWN"]


class ReconciliationService:
    def __init__(self, repository: TradeRepository, exchange: ExchangeAdapter, ledger: PositionLedger) -> None:
        self.repository = repository
        self.exchange = exchange
        self.ledger = ledger

    async def sync(self, config: AppConfig) -> dict:
        synced_orders = await self._sync_orders(config)
        synced_fills = await self._sync_fills(config)
        mark_price = await self._mark_price(config)
        ledger_result = self.ledger.rebuild_from_fills(config, mark_price=mark_price)
        exchange_positions = await self._sync_exchange_positions(config)
        balance_status = await self._check_spot_balance(config, ledger_result.position)
        if ledger_result.unreconciled:
            self.repository.insert_reconciliation_event(
                ReconciliationEvent(
                    severity="CRITICAL",
                    kind="pnl_unreconciled",
                    message="Fill ledger contains exits without matching entries; PnL is marked unreconciled.",
                    exchange=config.exchange.name,
                    market_type=config.trading.market_type,
                    symbol=config.trading.symbol,
                )
            )
        status = self.repository.reconciliation_status()
        return {
            **status,
            "synced_orders": synced_orders,
            "synced_fills": synced_fills,
            "position": ledger_result.position,
            "pnl": ledger_result.pnl,
            "exchange_positions": exchange_positions,
            "balance_status": balance_status,
            "synced_at": datetime.now(UTC).isoformat(),
        }

    async def _sync_orders(self, config: AppConfig) -> int:
        count = 0
        local_orders = self.repository.list_orders(status=ACTIVE, symbol=config.trading.symbol, limit=500)
        exchange_open = await self.exchange.fetch_open_orders(config, config.trading.symbol)
        open_by_id = {order.exchange_order_id: order for order in exchange_open if order.exchange_order_id}

        for local in local_orders:
            exchange_order: ExchangeOrder | None = None
            if local["exchange_order_id"]:
                try:
                    exchange_order = await self.exchange.fetch_order_status(config, local["exchange_order_id"], local["symbol"])
                except Exception as exc:
                    exchange_order = open_by_id.get(local["exchange_order_id"])
                    if exchange_order is None:
                        self.repository.update_order(local["id"], status="UNKNOWN")
                        self.repository.insert_reconciliation_event(
                            ReconciliationEvent(
                                severity="CRITICAL",
                                kind="order_missing_on_exchange",
                                message=f"Local order {local['id']} could not be confirmed on exchange: {exc}",
                                exchange=config.exchange.name,
                                market_type=config.trading.market_type,
                                symbol=local["symbol"],
                            )
                        )
                        continue
            elif local["status"] in {"NEW", "SENT"}:
                self.repository.update_order(local["id"], status="UNKNOWN")
                continue

            if exchange_order:
                self.repository.update_order(
                    local["id"],
                    status=exchange_order.status,
                    exchange_order_id=exchange_order.exchange_order_id,
                    filled_size=exchange_order.filled_size,
                    remaining_size=exchange_order.remaining_size,
                    average_price=exchange_order.average_price,
                    raw_payload=encode_raw(exchange_order.raw_payload),
                )
                count += 1

        local_exchange_ids = {order["exchange_order_id"] for order in self.repository.list_orders(symbol=config.trading.symbol, limit=1000) if order["exchange_order_id"]}
        for exchange_order in exchange_open:
            if exchange_order.exchange_order_id and exchange_order.exchange_order_id not in local_exchange_ids:
                self.repository.insert_reconciliation_event(
                    ReconciliationEvent(
                        severity="CRITICAL",
                        kind="exchange_only_order",
                        message=f"Exchange has open order {exchange_order.exchange_order_id} not present locally.",
                        exchange=config.exchange.name,
                        market_type=config.trading.market_type,
                        symbol=exchange_order.symbol,
                    )
                )
        return count

    async def _sync_fills(self, config: AppConfig) -> int:
        fills = await self.exchange.fetch_my_trades(config, config.trading.symbol)
        inserted = 0
        for fill in fills:
            if self.repository.upsert_fill(fill):
                inserted += 1
            local_order = self.repository.get_order_by_exchange_id(config.exchange.name, fill.exchange_order_id)
            if local_order is None:
                self.repository.insert_reconciliation_event(
                    ReconciliationEvent(
                        severity="CRITICAL",
                        kind="exchange_only_fill",
                        message=f"Exchange fill {fill.exchange_trade_id} references unknown order {fill.exchange_order_id}.",
                        exchange=config.exchange.name,
                        market_type=config.trading.market_type,
                        symbol=fill.symbol,
                    )
                )
        return inserted

    async def _mark_price(self, config: AppConfig) -> float | None:
        try:
            snapshot = await self.exchange.fetch_order_book(config)
            return snapshot.mid
        except Exception:
            return None

    async def _sync_exchange_positions(self, config: AppConfig) -> list[dict]:
        if config.trading.market_type != "swap":
            return []
        positions = await self.exchange.fetch_positions(config)
        matched = []
        for position in positions:
            symbol = str(position.get("symbol") or "").upper()
            if symbol != config.trading.symbol:
                continue
            matched.append(position)
            base, quote = split_symbol(config.trading.symbol)
            contracts = float(position.get("contracts") or position.get("size") or position.get("contractSize") or 0.0)
            side = str(position.get("side") or "").lower()
            signed_size = -abs(contracts) if side == "short" else contracts
            entry = float(position.get("entryPrice") or position.get("average") or 0.0)
            mark = float(position.get("markPrice") or position.get("lastPrice") or entry or 0.0)
            realized = float(position.get("realizedPnl") or position.get("realisedPnl") or 0.0)
            unrealized = float(position.get("unrealizedPnl") or position.get("unrealizedProfit") or 0.0)
            previous = self.repository.latest_pnl_snapshot(config.trading.symbol)
            self.repository.upsert_position(
                Position(
                    exchange=config.exchange.name,
                    market_type=config.trading.market_type,
                    symbol=config.trading.symbol,
                    base_asset=base,
                    quote_asset=quote,
                    size=signed_size,
                    average_entry_price=entry,
                    realized_pnl=realized,
                    unrealized_pnl=unrealized,
                    mark_price=mark,
                    source="exchange",
                    last_synced_at=datetime.now(UTC).isoformat(),
                )
            )
            self.repository.insert_pnl_snapshot(
                exchange=config.exchange.name,
                market_type=config.trading.market_type,
                symbol=config.trading.symbol,
                realized_pnl=realized,
                unrealized_pnl=unrealized,
                fees=sum(float(fill["fee"]) for fill in self.repository.list_fills(symbol=config.trading.symbol, limit=10000)),
                source="exchange-position",
            )
            realized_delta = realized - float(previous.get("realized_pnl") or 0.0)
            if realized_delta < 0 and config.risk.cooldown_after_loss_seconds > 0:
                cooldown = datetime.now(UTC) + timedelta(seconds=config.risk.cooldown_after_loss_seconds)
                self.repository.update_risk_state(cooldown.isoformat(), datetime.now(UTC).isoformat())
        if not matched:
            local_positions = self.repository.list_positions(symbol=config.trading.symbol)
            local_size = float(local_positions[0]["size"]) if local_positions else 0.0
            if abs(local_size) > 1e-12:
                self.repository.insert_reconciliation_event(
                    ReconciliationEvent(
                        severity="HIGH",
                        kind="exchange_position_missing",
                        message="No futures/perp exchange position returned for configured symbol while local ledger is non-flat.",
                        exchange=config.exchange.name,
                        market_type=config.trading.market_type,
                        symbol=config.trading.symbol,
                    )
                )
            else:
                self.repository.resolve_reconciliation_events(
                    config.exchange.name,
                    config.trading.market_type,
                    config.trading.symbol,
                    kind="exchange_position_missing",
                )
        return matched

    async def _check_spot_balance(self, config: AppConfig, position: dict) -> dict:
        if config.trading.market_type != "spot":
            return {"status": "not_applicable"}
        balances = await self.exchange.fetch_balances(config)
        base, quote = split_symbol(config.trading.symbol)
        free = balances.get("free") if isinstance(balances, dict) else {}
        total = balances.get("total") if isinstance(balances, dict) else {}
        base_total = float((total or {}).get(base, (free or {}).get(base, 0.0)) or 0.0)
        local_size = float(position["size"])
        drift = abs(base_total - local_size)
        if drift > 1e-8:
            self.repository.insert_reconciliation_event(
                ReconciliationEvent(
                    severity="CRITICAL",
                    kind="balance_drift",
                    message=f"Internal {base} position {local_size} differs from exchange balance {base_total}.",
                    exchange=config.exchange.name,
                    market_type=config.trading.market_type,
                    symbol=config.trading.symbol,
                )
            )
            return {"status": "DRIFT", "base": base, "exchange_total": base_total, "local_size": local_size, "drift": drift}
        return {"status": "OK", "base": base, "exchange_total": base_total, "local_size": local_size, "drift": drift}
