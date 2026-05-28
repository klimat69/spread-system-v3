from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict

from .config import config_service
from .database import trade_repository
from .exchange import exchange_adapter
from .credentials import credential_store
from .ledger import PositionLedger
from .reconciliation import ReconciliationService


async def validate(symbol: str | None, market_type: str | None, exchange_name: str | None = None) -> dict:
    config = config_service.load(force=True)
    if exchange_name:
        config.exchange.name = exchange_name  # type: ignore[assignment]
    if symbol:
        config.trading.symbol = symbol.upper()
    if market_type:
        config.trading.market_type = market_type  # type: ignore[assignment]

    creds = credential_store.get(config.exchange.name)
    has_creds = bool(
        (creds and creds.api_key and creds.api_secret)
        or (config.exchange.api_key and config.exchange.api_secret)
    )

    if not has_creds:
        result = trade_repository.insert_validation_result(
            config.exchange.name,
            config.trading.market_type,
            config.trading.symbol,
            "BLOCKED_NO_CREDENTIALS",
            "Real exchange validation requires API key and secret.",
            {"orders_checked": 0, "fills_checked": 0},
        )
        return result

    service = ReconciliationService(trade_repository, exchange_adapter, PositionLedger(trade_repository))
    sync = await service.sync(config)
    orders = trade_repository.list_orders(symbol=config.trading.symbol, limit=5000)
    fills = trade_repository.list_fills(symbol=config.trading.symbol, limit=5000)
    reconciliation = trade_repository.reconciliation_status()

    missing_order_id = [order for order in orders if order["status"] not in {"REJECTED", "CANCELLED", "UNKNOWN"} and not order["exchange_order_id"]]
    invalid_fills = [fill for fill in fills if not fill["exchange_order_id"] or not fill["exchange_trade_id"]]
    status = "PASSED"
    message = "Exchange validation passed."
    if missing_order_id or invalid_fills or reconciliation["blocking"]:
        status = "FAILED"
        message = "Exchange validation failed; trading remains blocked."

    return trade_repository.insert_validation_result(
        config.exchange.name,
        config.trading.market_type,
        config.trading.symbol,
        status,
        message,
        {
            "sync": sync,
            "orders_checked": len(orders),
            "fills_checked": len(fills),
            "missing_order_id": missing_order_id,
            "invalid_fills": invalid_fills,
            "reconciliation": reconciliation,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate exchange truth against local ledger.")
    parser.add_argument("--symbol")
    parser.add_argument("--market-type", choices=["spot", "swap"])
    parser.add_argument("--exchange", choices=["mexc"], default="mexc")
    args = parser.parse_args()
    result = asyncio.run(validate(args.symbol, args.market_type, args.exchange))
    print(asdict(result) if hasattr(result, "__dataclass_fields__") else result)
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
