from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from .config import config_service
from .database import Trade, trade_repository
from .exchange import exchange_adapter
from .risk import RiskEngine
from .strategy import StrategyEngine
from .websocket import manager

logger = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self) -> None:
        self.strategy = StrategyEngine()
        self.risk = RiskEngine(trade_repository)
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._last_error: str | None = None
        self._last_metrics: dict = {}
        self._blocked_reason: str | None = None

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
            **self._last_metrics,
            **self.risk.status(),
        }

    async def start(self) -> dict:
        if self._running:
            return self.status()
        self._running = True
        self._task = asyncio.create_task(self._loop())
        trade_repository.insert_event("info", "Trading engine started")
        await manager.broadcast({"type": "status", "status": self.status()})
        return self.status()

    async def stop(self) -> dict:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        trade_repository.insert_event("info", "Trading engine stopped")
        await manager.broadcast({"type": "status", "status": self.status()})
        return self.status()

    async def _loop(self) -> None:
        while self._running:
            started = datetime.now(UTC)
            try:
                await self._cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("Trading cycle failed")
                trade_repository.insert_event("error", f"Trading cycle failed: {exc}")
                await manager.broadcast({"type": "error", "message": str(exc), "status": self.status()})
            config = config_service.load()
            elapsed = (datetime.now(UTC) - started).total_seconds()
            await asyncio.sleep(max(config.trading.cycle_interval_seconds - elapsed, 0.1))

    async def _cycle(self) -> None:
        config = config_service.load()
        snapshot = await exchange_adapter.fetch_order_book(config)
        decision = self.strategy.evaluate(snapshot, config)
        self._last_metrics = {
            "last_update": datetime.now(UTC).isoformat(),
            "spread": decision.spread,
            "edge": decision.edge,
            "volatility": decision.volatility,
            "imbalance": decision.imbalance,
            "liquidity": decision.liquidity,
        }
        self._blocked_reason = None
        trade_payload = None
        if not decision.should_trade:
            self._blocked_reason = decision.reason
        else:
            price = snapshot.ask if decision.side == "buy" else snapshot.bid
            risk = self.risk.check(config, decision.side, price, config.trading.order_size)
            if not risk.allowed:
                self._blocked_reason = risk.reason
            else:
                execution = await exchange_adapter.execute(config, decision.side, price, decision.edge)
                trade_payload = trade_repository.insert_trade(
                    Trade(
                        timestamp=datetime.now(UTC).isoformat(),
                        symbol=execution.symbol,
                        side=execution.side,
                        price=execution.price,
                        size=execution.size,
                        pnl=execution.pnl,
                        fee=execution.fee,
                        exchange=f"{execution.exchange}:{execution.mode}",
                    )
                )
                self.risk.record_fill(execution.side, execution.size, execution.pnl - execution.fee, config)
        self._last_error = None
        await manager.broadcast({
            "type": "live",
            "status": self.status(),
            "pnl": trade_repository.pnl_summary(),
            "trade": trade_payload,
        })


trading_engine = TradingEngine()
