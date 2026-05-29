from app.mexc_symbols import (
    mexc_display_symbol,
    mexc_futures_ws_symbol,
    mexc_web_url,
    resolve_mexc_trading_symbol,
    sort_symbols,
    tradingview_symbol,
)


def test_mexc_display_swap():
    assert mexc_display_symbol("BTC/USDT:USDT", "swap") == "BTCUSDT"


def test_mexc_display_swap_gold():
    assert mexc_display_symbol("XAUT/USDT:USDT", "swap") == "GOLD(XAUT)USDT"


def test_mexc_display_spot_gold():
    assert mexc_display_symbol("GOLD(XAUT)/USDC", "spot") == "GOLD(XAUT)USDC"


def test_mexc_futures_ws_gold_maps_to_xaut():
    assert mexc_futures_ws_symbol("GOLD(XAUT)/USDT:USDT") == "XAUT_USDT"
    assert mexc_futures_ws_symbol("GOLD(XAUT)/USDC") == "XAUT_USDC"
    assert mexc_futures_ws_symbol("XAUT/USDT:USDT") == "XAUT_USDT"
    assert mexc_futures_ws_symbol("BTC/USDT:USDT") == "BTC_USDT"


def test_mexc_web_urls():
    assert "futures/XAUT_USDT" in mexc_web_url("XAUT/USDT:USDT", "swap")
    assert "futures/BTC_USDT" in mexc_web_url("BTC/USDT:USDT", "swap")
    assert "exchange/GOLD(XAUT)_USDC" in mexc_web_url("GOLD(XAUT)/USDC", "spot")


def test_tradingview_xaut_mapping():
    assert tradingview_symbol("GOLD(XAUT)/USDC", "spot") == "MEXC:XAUTUSDC"
    assert tradingview_symbol("GOLD(XAUT)/USDT:USDT", "swap") == "MEXC:XAUTUSDT.P"
    assert tradingview_symbol("XAUT/USDT:USDT", "swap") == "MEXC:XAUTUSDT.P"


def test_resolve_gold_futures_from_spot_ticker():
    available = ["BTC/USDT:USDT", "XAUT/USDT:USDT", "ETH/USDT:USDT"]
    assert resolve_mexc_trading_symbol("GOLD(XAUT)/USDC", "swap", available) == "XAUT/USDT:USDT"


def test_sort_popular_first():
    symbols = ["AAA/USDT:USDT", "BTC/USDT:USDT", "ETH/USDT:USDT", "XAUT/USDT:USDT"]
    popular, rest = sort_symbols(symbols, "swap", "USDT")
    assert popular[0] == "XAUT/USDT:USDT"
    assert "BTC/USDT:USDT" in popular
    assert "AAA/USDT:USDT" in rest
