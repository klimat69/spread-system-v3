"""MEXC symbol catalog helpers — display names and URLs aligned with mexc.com."""

from __future__ import annotations

from typing import Any

POPULAR_SWAP_USDT: tuple[str, ...] = (
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
    "BNB/USDT:USDT",
    "ADA/USDT:USDT",
    "AVAX/USDT:USDT",
    "LINK/USDT:USDT",
    "XAUT/USDT:USDT",
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
    return f"{base.upper()}{quote.upper()}"


def mexc_contract_id(symbol: str) -> str:
    """CCXT symbol -> MEXC URL segment (BTC_USDT, GOLD(XAUT)_USDC)."""
    return symbol.split(":")[0].replace("/", "_").upper()


def mexc_web_url(symbol: str, market_type: str) -> str:
    contract = mexc_contract_id(symbol)
    if market_type == "swap":
        return f"https://www.mexc.com/ru-RU/futures/{contract}"
    return f"https://www.mexc.com/ru-RU/exchange/{contract}"


def tradingview_symbol(symbol: str, market_type: str) -> str:
    """Best-effort TradingView symbol for MEXC embed."""
    pair = symbol.split(":")[0]
    base = pair.split("/")[0].upper()
    quote = pair.split("/")[1].upper() if "/" in pair else "USDT"
    if "XAUT" in base or "GOLD" in base:
        tv_base = "XAUT"
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
    elif "GOLD" in symbol.upper() and market_type == "swap" and "USDC" in symbol.upper():
        note = "GOLD/USDC обычно доступен на споте; во фьючерсах ищите XAUT/USDT или GOLD(XAUT)/USDT."
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
