from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
import time

from .config import config_service
from .database import trade_repository
from .ledger import PositionLedger
from .market_data import market_data_engine
from .market_state import MarketState
from .order_manager import OrderManager
from .reconciliation import ReconciliationService
from .risk import RiskEngine
from .simple_scalp import SimpleScalpEngine
from .websocket import manager

logger = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self) -> None:
        self.strategy = SimpleScalpEngine()
        self.risk = RiskEngine(trade_repository)
        self.ledger = PositionLedger(trade_repository)
        from .exchange import exchange_adapter

        self.reconciliation = ReconciliationService(trade_repository, exchange_adapter, self.ledger)
        self.order_manager = OrderManager()
        self._running = False
        self._subscribed = False
        self._last_error: str | None = None
        self._last_metrics: dict = {}
        self._blocked_reason: str | None = None
        self._dry_run_orders: list[dict] = []
        self._last_market_broadcast_ns: int = 0
        self._last_status_broadcast_ns: int = 0

    @property
    def running(self) -> bool:
        return self._running

    def status(self) -> dict:
        config = config_service.load()
        return {
            "running": self._running,
            "mode": config.trading.mode,
            "exchange": config.exchange.name,
            "symbol": config.trading.symbol,
            "last_error": self._last_error,
            "blocked_reason": self._blocked_reason,
            "last_update": None,
            "spread": 0.0,
            "edge": 0.0,
            "volatility": 0.0,
            "imbalance": 0.0,
            "liquidity": 0.0,
            "bid_pressure": 0.0,
            "ask_pressure": 0.0,
            "tape_aggression": 0.0,
            "tape_buy_notional": 0.0,
            "tape_sell_notional": 0.0,
            "tape_burst_ratio": 0.0,
            "micro_trend": "neutral",
            "entry_reason": None,
            "exit_reason": None,
            "expected_holding_seconds": config.strategy.max_holding_seconds,
            "liquidity_walls": [],
            "validation": trade_repository.latest_validation_result(config.exchange.name, config.trading.market_type, config.trading.symbol),
            "market_data": self._last_metrics.get("market_data", {}),
            "auto_trade_enabled": config.trading.auto_trade_enabled,
            "use_realtime_dom_engine": config.trading.use_realtime_dom_engine,
            "active_order": self.order_manager.active.local_order_id if self.order_manager.active else None,
            "dry_run_orders": self._dry_run_orders[-20:],
            **self._last_metrics,
            **self.risk.status(),
        }

    async def start(self) -> dict:
        if self._running:
            return self.status()
        config = config_service.load()
        await market_data_engine.ensure_started(config)
        self._running = True
        if not self._subscribed:
            market_data_engine.subscribe_orderbook_updates(self._on_market_event)
            market_data_engine.subscribe_trade_updates(self._on_market_event)
            self._subscribed = True
        trade_repository.insert_event("info", "Trading engine started")
        await manager.broadcast({"type": "status", "status": self.status()})
        return self.status()

    async def stop(self) -> dict:
        self._running = False
        config = config_service.load()
        if self.order_manager.active:
            try:
                await self.order_manager.cancel_active(config, reason="engine_stopped")
            except Exception:
                logger.exception("Failed to cancel active order while stopping")
        await market_data_engine.stop()
        trade_repository.insert_event("info", "Trading engine stopped")
        await manager.broadcast({"type": "status", "status": self.status()})
        return self.status()

    async def _on_market_event(self, payload: dict) -> None:
        if not self._running:
            return
        state_payload = payload.get("state")
        if not isinstance(state_payload, dict):
            return
        config = config_service.load()
        if not config.trading.use_realtime_dom_engine:
            return
        state = self._state_from_payload(state_payload)
        now_ns = time.monotonic_ns()
        self._last_metrics = {
            "last_update": state.last_update,
            "spread": state.spread,
            "imbalance": state.imbalance,
            "market_data": {
                "status": state.ws_status,
                "reason": state.ws_reason,
                "sequence": state.sequence,
                "last_book_event_at": state.last_update,
            },
        }
        if now_ns - self._last_market_broadcast_ns > 80_000_000:  # ~12.5fps
            self._last_market_broadcast_ns = now_ns
            frame: dict = {"type": "market", "state": state_payload}
            if isinstance(payload.get("dom_delta"), dict):
                frame["dom_delta"] = payload["dom_delta"]
            if isinstance(payload.get("tape_trade"), dict):
                frame["tape_trade"] = payload["tape_trade"]
            await manager.broadcast(frame)
        await self._evaluate_event_driven(state)
        if now_ns - self._last_status_broadcast_ns > 200_000_000:  # 5fps status
            self._last_status_broadcast_ns = now_ns
            await manager.broadcast({"type": "status", "status": self.status()})

    async def _evaluate_event_driven(self, state: MarketState) -> None:
        config = config_service.load()
        if state.ws_status != "OK":
            self._blocked_reason = f"market_data_unhealthy:{state.ws_reason}"
            return
        if not config.trading.auto_trade_enabled:
            self._blocked_reason = "auto_trade_disabled"
            return

        decision = self.strategy.evaluate(state, config)
        self._blocked_reason = decision.reason if not decision.should_enter else None

        if config.trading.mode == "paper":
            await self._handle_dry_run(state, decision, config)
            return

        validation = trade_repository.latest_validation_result(config.exchange.name, config.trading.market_type, config.trading.symbol)
        if validation["status"] != "PASSED" or not config.trading.live_trading_enabled:
            self._blocked_reason = "live_validation_required"
            return

        active = self.order_manager.active
        if active:
            stale_after = config.simple_scalp.stale_order_after_seconds
            created_at = datetime.fromisoformat(active.created_at.replace("Z", "+00:00"))
            age = (datetime.now(UTC) - created_at).total_seconds()
            move_bps = abs(((state.best_bid if active.side == "buy" else state.best_ask) - active.requested_price) / active.requested_price) * 10_000
            should_replace = move_bps >= config.simple_scalp.replace_move_bps
            if decision.should_exit or age >= stale_after or should_replace:
                await self.order_manager.cancel_active(config, reason="exit_or_stale")
                await manager.broadcast({"type": "orders", "orders": trade_repository.list_orders(limit=30)})

        if self.order_manager.active is None and decision.should_enter:
            price = state.best_bid if decision.signal == "buy" else state.best_ask
            risk = self.risk.check(config, decision.signal, price, config.trading.order_size)
            if not risk.allowed:
                self._blocked_reason = risk.reason
                return
            open_orders = trade_repository.list_orders(status=["NEW", "SENT", "OPEN", "PARTIAL", "UNKNOWN"], symbol=config.trading.symbol, limit=50)
            if len(open_orders) >= config.strategy.max_open_orders_per_symbol:
                self._blocked_reason = "max_open_orders_reached"
                return
            await self.order_manager.place_limit(config, decision.signal, price, config.trading.order_size)
            await manager.broadcast({"type": "orders", "orders": trade_repository.list_orders(limit=30)})

    async def _handle_dry_run(self, state: MarketState, decision, config) -> None:
        if decision.should_enter and decision.signal in {"buy", "sell"}:
            price = state.best_bid if decision.signal == "buy" else state.best_ask
            event = {
                "id": f"dry-{int(time.time() * 1000)}",
                "timestamp": datetime.now(UTC).isoformat(),
                "side": decision.signal,
                "price": price,
                "size": config.trading.order_size,
                "reason": decision.reason,
                "status": "OPEN",
            }
            self._dry_run_orders.append(event)
            self._dry_run_orders = self._dry_run_orders[-100:]
            await manager.broadcast({"type": "dry_run", "event": event, "orders": self._dry_run_orders[-30:]})
        elif decision.should_exit and self._dry_run_orders:
            latest = self._dry_run_orders[-1]
            latest["status"] = "CLOSED"
            latest["closed_at"] = datetime.now(UTC).isoformat()
            latest["exit_reason"] = decision.reason
            await manager.broadcast({"type": "dry_run", "event": latest, "orders": self._dry_run_orders[-30:]})

    def _state_from_payload(self, payload: dict) -> MarketState:
        state = MarketState()
        state.exchange = str(payload.get("exchange") or "mexc")
        state.market_type = str(payload.get("market_type") or "swap")
        state.symbol = str(payload.get("symbol") or "BTC/USDT")
        state.best_bid = float(payload.get("best_bid") or 0.0)
        state.best_ask = float(payload.get("best_ask") or 0.0)
        state.spread = float(payload.get("spread") or 0.0)
        state.imbalance = float(payload.get("imbalance") or 0.0)
        state.ws_status = str(payload.get("ws_status") or "STOPPED")
        state.ws_reason = str(payload.get("ws_reason") or "market_data_unavailable")
        state.feed_state = str(payload.get("feed_state") or "RECOVERING")
        state.last_update = payload.get("last_update")
        state.sequence = payload.get("sequence")
        state.clock_skew_ms = float(payload.get("clock_skew_ms") or 0.0)
        state.tape_velocity_1s = float(payload.get("tape_velocity_1s") or 0.0)
        state.buy_aggression_rate = float(payload.get("buy_aggression_rate") or 0.0)
        state.sell_aggression_rate = float(payload.get("sell_aggression_rate") or 0.0)
        state.delta_velocity = float(payload.get("delta_velocity") or 0.0)
        for item in payload.get("recent_trades") or []:
            try:
                from .strategy import TapePrint

                state.recent_trades.append(
                    TapePrint(
                        price=float(item.get("price") or 0.0),
                        size=float(item.get("size") or 0.0),
                        side=str(item.get("side") or "buy"),
                        timestamp=str(item.get("timestamp") or datetime.now(UTC).isoformat()),
                    )
                )
            except Exception:
                continue
        return state

    def _current_position_opened_at(self, symbol: str) -> datetime | None:
        fills = trade_repository.list_fills(symbol=symbol, limit=10000)
        opened_at: datetime | None = None
        current_size = 0.0
        for fill in fills:
            signed_size = float(fill["size"]) if fill["side"] == "buy" else -float(fill["size"])
            previous_size = current_size
            current_size += signed_size
            try:
                fill_time = datetime.fromisoformat(fill["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if fill_time.tzinfo is None:
                fill_time = fill_time.replace(tzinfo=UTC)
            if abs(previous_size) <= 1e-12 and abs(current_size) > 1e-12:
                opened_at = fill_time
            elif previous_size * current_size < 0:
                opened_at = fill_time
            elif abs(current_size) <= 1e-12:
                opened_at = None
        if abs(current_size) <= 1e-12:
            return None
        return opened_at

    def _holding_time_exit_reason(self, config) -> str | None:
        positions = trade_repository.list_positions(symbol=config.trading.symbol)
        if not positions or abs(float(positions[0]["size"])) <= 1e-12:
            return None
        opened_at = self._current_position_opened_at(config.trading.symbol)
        if opened_at is None:
            return None
        age = (datetime.now(UTC) - opened_at).total_seconds()
        return "max_holding_time_elapsed" if age >= config.strategy.max_holding_seconds else None

    async def _broadcast_state(self, trade_payload: dict | None = None) -> None:
        self._last_error = None
        await manager.broadcast(
            {
                "type": "live",
                "status": self.status(),
                "pnl": trade_repository.pnl_summary(),
                "trade": trade_payload,
                "orders": trade_repository.list_orders(limit=20),
                "fills": trade_repository.list_fills(limit=50),
                "positions": trade_repository.list_positions(),
                "reconciliation": trade_repository.reconciliation_status(),
            }
        )


trading_engine = TradingEngine()
