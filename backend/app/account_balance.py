from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .config import AppConfig
from .credentials import credential_store
from .exchange import ExchangeAdapter
from .ledger import split_symbol


def _has_credentials(config: AppConfig) -> bool:
    creds = credential_store.get(config.exchange.name)
    return bool(
        (creds and creds.api_key and creds.api_secret)
        or (config.exchange.api_key and config.exchange.api_secret)
    )


def _asset_amount(balances: dict[str, Any], asset: str, bucket: str = "free") -> float:
    data = balances.get(bucket) if isinstance(balances, dict) else None
    if not isinstance(data, dict):
        return 0.0
    try:
        return float(data.get(asset, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


async def fetch_account_balance_snapshot(config: AppConfig, exchange: ExchangeAdapter) -> dict[str, Any]:
    if not _has_credentials(config):
        return {"ok": False, "reason": "no_credentials"}

    base, quote = split_symbol(config.trading.symbol)
    try:
        balances = await exchange.fetch_balances(config)
    except Exception as exc:
        return {"ok": False, "reason": "fetch_failed", "message": str(exc)}

    quote_free = _asset_amount(balances, quote, "free")
    quote_total = _asset_amount(balances, quote, "total")
    base_free = _asset_amount(balances, base, "free")
    base_total = _asset_amount(balances, base, "total")

    position_size = 0.0
    unrealized_pnl = 0.0
    if config.trading.market_type == "swap":
        try:
            positions = await exchange.fetch_positions(config)
            for row in positions:
                sym = str(row.get("symbol") or "").upper()
                if sym and sym != config.trading.symbol.upper():
                    continue
                contracts = row.get("contracts")
                if contracts is None:
                    contracts = row.get("size")
                position_size = float(contracts or 0)
                unrealized_pnl = float(row.get("unrealizedPnl") or row.get("unrealized_pnl") or 0)
                break
        except Exception:
            pass

    return {
        "ok": True,
        "market_type": config.trading.market_type,
        "symbol": config.trading.symbol,
        "base": base,
        "quote": quote,
        "base_free": base_free,
        "base_total": base_total,
        "quote_free": quote_free,
        "quote_total": quote_total,
        "position_size": position_size,
        "unrealized_pnl": unrealized_pnl,
        "updated_at": datetime.now(UTC).isoformat(),
    }
