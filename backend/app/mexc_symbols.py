"""MEXC symbol catalog helpers — display names and URLs aligned with mexc.com."""

from __future__ import annotations

from typing import Any, Iterable

# MEXC perpetual WebSocket + REST contract id (see mexc.com/futures/XAUT_USDT).
GOLD_FUTURES_WS_SYMBOL = "XAUT_USDT"
GOLD_FUTURES_CCXT_CANDIDATES: tuple[str, ...] = (
    "XAUT/USDT:USDT",
    "GOLD(XAUT)/USDT:USDT",
    "XAUT/USDT",
)

POPULAR_SWAP_USDT: tuple[str, ...] = (
    "XAUT/USDT:USDT",
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
    "BNB/USDT:USDT",
    "ADA/USDT:USDT",
    "AVAX/USDT:USDT",
    "LINK/USDT:USDT",
    "OG/USDT:USDT",
)

POPULAR_SPOT: dict[str, tuple[str, ...]] = {
    "USDT": (
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "XAUT/USDT",
        "GOLD(XAUT)/USDT",
        "OG/USDT",
    ),
    "USDC": (
        "BTC/USDC",
        "ETH/USDC",
        "XAUT/USDC",
        "GOLD(XAUT)/USDC",
        "OG/USDC",
    ),
}


def mexc_display_symbol(symbol: str, market_type: str) -> str:
    """CCXT symbol -> MEXC UI ticker (e.g. BTC/USDT:USDT -> BTCUSDT)."""
    pair = symbol.split(":")[0]
    if "/" not in pair:
        return pair.upper()
    base, quote = pair.split("/", 1)
    if market_type == "swap" and is_gold_or_xaut(symbol):
        return f"GOLD(XAUT){quote.upper()}"
    return f"{base.upper()}{quote.upper()}"


def _base_quote(symbol: str) -> tuple[str, str]:
    pair = symbol.split(":")[0]
    if "/" not in pair:
        return pair.upper(), "USDT"
    base, quote = pair.split("/", 1)
    return base.upper(), quote.upper()


def is_gold_or_xaut(symbol: str) -> bool:
    base, _ = _base_quote(symbol)
    return "XAUT" in base or "GOLD" in base


def mexc_futures_ws_symbol(symbol: str) -> str:
    """CCXT symbol -> MEXC futures WS/REST contract (XAUT_USDT, BTC_USDT)."""
    base, quote = _base_quote(symbol)
    if "XAUT" in base or "GOLD" in base:
        return f"XAUT_{quote}"
    return f"{base}_{quote}"


def mexc_spot_url_segment(symbol: str) -> str:
    """CCXT symbol -> MEXC spot exchange URL segment."""
    pair = symbol.split(":")[0]
    if "/" not in pair:
        return pair.upper()
    base, quote = pair.split("/", 1)
    if is_gold_or_xaut(symbol):
        if "GOLD" in base.upper():
            return f"GOLD(XAUT)_{quote.upper()}"
        return f"XAUT_{quote.upper()}"
    return f"{base.upper()}_{quote.upper()}"


def mexc_contract_id(symbol: str, market_type: str = "swap") -> str:
    """CCXT symbol -> MEXC URL segment."""
    if market_type == "spot":
        return mexc_spot_url_segment(symbol)
    return mexc_futures_ws_symbol(symbol)


def resolve_mexc_trading_symbol(
    symbol: str,
    market_type: str,
    available: Iterable[str] | None = None,
) -> str:
    """Map UI/legacy tickers to a CCXT symbol that exists for the selected market."""
    normalized = symbol.strip().upper()
    if not normalized:
        return normalized
    available_list = list(available or [])
    by_upper = {item.upper(): item for item in available_list}

    if market_type == "swap":
        if is_gold_or_xaut(normalized):
            for candidate in GOLD_FUTURES_CCXT_CANDIDATES:
                hit = by_upper.get(candidate.upper())
                if hit:
                    return hit.upper()
            if "USDC" in normalized:
                return "XAUT/USDT:USDT"
            if ":USDT" not in normalized and normalized.endswith("/USDT"):
                return f"{normalized}:USDT"
            return "XAUT/USDT:USDT"
    elif market_type == "spot" and is_gold_or_xaut(normalized) and "USDC" in normalized:
        for candidate in ("GOLD(XAUT)/USDC", "XAUT/USDC"):
            hit = by_upper.get(candidate.upper())
            if hit:
                return hit.upper()
    return normalized


def mexc_web_url(symbol: str, market_type: str) -> str:
    contract = mexc_contract_id(symbol, market_type)
    if market_type == "swap":
        return f"https://www.mexc.com/ru-RU/futures/{contract}"
    return f"https://www.mexc.com/ru-RU/exchange/{contract}"


def tradingview_symbol(symbol: str, market_type: str) -> str:
    """Best-effort TradingView symbol for MEXC embed."""
    base, quote = _base_quote(symbol)
    if is_gold_or_xaut(symbol):
        tv_base = "XAUT"
        if market_type == "swap":
            quote = "USDT"
    else:
        tv_base = "".join(ch for ch in base if ch.isalnum())
    ticker = f"{tv_base}{quote}"
    return f"MEXC:{ticker}.P" if market_type == "swap" else f"MEXC:{ticker}"


def symbol_meta(symbol: str, market_type: str, market: dict[str, Any] | None = None) -> dict[str, str]:
    display = mexc_display_symbol(symbol, market_type)
    quote = str((market or {}).get("quote") or symbol.split(":")[0].split("/")[-1]).upper()
    kind = "perpetual" if market_type == "swap" else "spot"
    if market_type == "swap" and quote != "USDT":
        note = "На MEXC большинство perpetual — в USDT; проверьте наличие контракта на сайте."
    elif market_type == "swap" and is_gold_or_xaut(symbol):
        note = "Контракт MEXC: XAUT_USDT perpetual — стакан и сделки с contract.mexc.com."
    elif "GOLD" in symbol.upper() and market_type == "swap" and "USDC" in symbol.upper():
        note = "GOLD/USDC обычно доступен на споте; во фьючерсах выберите GOLD Futures (USDT)."
    else:
        note = ""
    return {
        "display": display,
        "quote": quote,
        "kind": kind,
        "mexc_url": mexc_web_url(symbol, market_type),
        "tradingview": tradingview_symbol(symbol, market_type),
        "note": note,
    }


def popular_for(market_type: str, quote: str) -> list[str]:
    if market_type == "swap" and quote.upper() == "USDT":
        return list(POPULAR_SWAP_USDT)
    return list(POPULAR_SPOT.get(quote.upper(), ()))


def sort_symbols(symbols: list[str], market_type: str, quote: str) -> tuple[list[str], list[str]]:
    popular = popular_for(market_type, quote)
    popular_set = set(popular)
    ordered_popular = [s for s in popular if s in symbols]
    rest = sorted([s for s in symbols if s not in popular_set], key=lambda s: mexc_display_symbol(s, market_type))
    return ordered_popular, rest
