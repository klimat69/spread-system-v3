from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from .config import AppConfig
from .database import OrderIntent, encode_raw, trade_repository
from .exchange import exchange_adapter


@dataclass(slots=True)
class OpenOrderState:
    local_order_id: int
    exchange_order_id: str | None
    side: str
    created_at: str
    requested_price: float
    requested_size: float


class OrderManager:
    def __init__(self) -> None:
        self._active: OpenOrderState | None = None

    @property
    def active(self) -> OpenOrderState | None:
        return self._active

    async def place_limit(self, config: AppConfig, side: str, price: float, size: float) -> dict:
        intent = OrderIntent(
            exchange=config.exchange.name,
            market_type=config.trading.market_type,
            symbol=config.trading.symbol,
            side=side,
            order_type="limit",
            requested_size=size,
            requested_price=price,
            client_order_id=f"spread-v3-{uuid4().hex}",
        )
        local_order = trade_repository.create_order(intent)
        trade_repository.update_order(local_order["id"], status="SENT")
        exchange_order = await exchange_adapter.submit_order(config, intent)
        saved = trade_repository.update_order(
            local_order["id"],
            status=exchange_order.status,
            exchange_order_id=exchange_order.exchange_order_id,
            filled_size=exchange_order.filled_size,
            remaining_size=exchange_order.remaining_size,
            average_price=exchange_order.average_price,
            raw_payload=encode_raw(exchange_order.raw_payload),
        )
        self._active = OpenOrderState(
            local_order_id=saved["id"],
            exchange_order_id=saved.get("exchange_order_id"),
            side=side,
            created_at=datetime.now(UTC).isoformat(),
            requested_price=price,
            requested_size=size,
        )
        return saved

    async def cancel_active(self, config: AppConfig, reason: str = "cancel") -> dict | None:
        if self._active is None:
            return None
        current = self._active
        if current.exchange_order_id:
            order = await exchange_adapter.cancel_order(config, current.exchange_order_id, config.trading.symbol)
            saved = trade_repository.update_order(
                current.local_order_id,
                status=order.status,
                filled_size=order.filled_size,
                remaining_size=order.remaining_size,
                average_price=order.average_price,
                raw_payload=encode_raw({"cancel_reason": reason, "payload": order.raw_payload}),
            )
            self._active = None
            return saved
        saved = trade_repository.update_order(
            current.local_order_id,
            status="CANCELLED",
            raw_payload=encode_raw({"cancel_reason": reason}),
        )
        self._active = None
        return saved
