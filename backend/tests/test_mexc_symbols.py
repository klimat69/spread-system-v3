from app.mexc_symbols import mexc_display_symbol, mexc_web_url, sort_symbols, tradingview_symbol


def test_mexc_display_swap():
    assert mexc_display_symbol("BTC/USDT:USDT", "swap") == "BTCUSDT"


def test_mexc_display_spot_gold():
    assert mexc_display_symbol("GOLD(XAUT)/USDC", "spot") == "GOLD(XAUT)USDC"


def test_mexc_web_urls():
    assert "futures/BTC_USDT" in mexc_web_url("BTC/USDT:USDT", "swap")
    assert "exchange/GOLD(XAUT)_USDC" in mexc_web_url("GOLD(XAUT)/USDC", "spot")


def test_tradingview_xaut_mapping():
    assert tradingview_symbol("GOLD(XAUT)/USDC", "spot") == "MEXC:XAUTUSDC"


def test_sort_popular_first():
    symbols = ["AAA/USDT:USDT", "BTC/USDT:USDT", "ETH/USDT:USDT"]
    popular, rest = sort_symbols(symbols, "swap", "USDT")
    assert popular[0] == "BTC/USDT:USDT"
    assert "AAA/USDT:USDT" in rest
