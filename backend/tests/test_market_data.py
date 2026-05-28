from datetime import UTC, datetime

import pytest

from app.config import AppConfig
from app.market_data import BookDelta, LocalOrderBook, MarketDataEngine, NativeFeedParser, TapeDelta, monotonic_ns
from app.strategy import OrderBookLevel


def test_local_orderbook_applies_sequence_continuous_delta():
    book = LocalOrderBook(depth=5)
    book.load_snapshot([[100.0, 2.0], [99.9, 1.0]], [[100.1, 2.0], [100.2, 1.0]], sequence=10)

    book.apply_delta(
        BookDelta(
            bids=[OrderBookLevel(100.0, 3.0)],
            asks=[OrderBookLevel(100.1, 0.0), OrderBookLevel(100.15, 2.0)],
            first_sequence=11,
            final_sequence=11,
            previous_sequence=None,
            event_time_ms=None,
            received_monotonic_ns=monotonic_ns(),
        )
    )

    bids, asks = book.levels()
    assert book.sequence == 11
    assert bids[0].size == 3.0
    assert asks[0].price == 100.15


def test_local_orderbook_rejects_sequence_gap():
    book = LocalOrderBook(depth=5)
    book.load_snapshot([[100.0, 2.0]], [[100.1, 2.0]], sequence=10)

    with pytest.raises(ValueError, match="sequence gap"):
        book.apply_delta(
            BookDelta(
                bids=[OrderBookLevel(100.0, 3.0)],
                asks=[],
                first_sequence=13,
                final_sequence=13,
                previous_sequence=None,
                event_time_ms=None,
                received_monotonic_ns=monotonic_ns(),
            )
        )


def test_local_orderbook_rejects_crossed_book():
    book = LocalOrderBook(depth=5)

    with pytest.raises(ValueError, match="crossed"):
        book.load_snapshot([[101.0, 2.0]], [[100.0, 2.0]], sequence=1)


def test_mexc_spot_parser_reads_depth_and_deals():
    config = AppConfig.model_validate(
        {**AppConfig().model_dump(), "trading": {**AppConfig().trading.model_dump(), "market_type": "spot"}}
    )
    parser = NativeFeedParser(config)
    depth, trades = parser.parse(
        {
            "c": "spot@public.limit.depth.v3.api@BTCUSDT@20",
            "t": 1_700_000_000_000,
            "d": {"bids": [["100", "3"]], "asks": [["101", "2"]], "r": 12},
        },
        monotonic_ns(),
    )
    assert depth[0].replace_snapshot is True
    assert depth[0].final_sequence == 12

    _, trades = parser.parse(
        {
            "c": "spot@public.deals.v3.api@BTCUSDT",
            "t": 1_700_000_000_001,
            "d": {"deals": [{"p": "101", "v": "0.5", "S": "1", "t": 1_700_000_000_001}]},
        },
        monotonic_ns(),
    )
    assert trades[0].side == "buy"


def test_mexc_futures_parser_reads_depth_and_deals():
    config = AppConfig.model_validate(
        {
            **AppConfig().model_dump(),
            "exchange": {"name": "mexc", "api_key": "", "api_secret": "", "password": "", "sandbox": False},
            "trading": {**AppConfig().trading.model_dump(), "market_type": "swap", "symbol": "BTC/USDT"},
        }
    )
    parser = NativeFeedParser(config)
    deltas, trades = parser.parse(
        {
            "channel": "push.depth",
            "symbol": "BTC_USDT",
            "ts": 1_700_000_000_000,
            "data": {"asks": [[100.1, 2, 5.0]], "bids": [[100.0, 1, 3.0]], "version": 42},
        },
        monotonic_ns(),
    )
    assert deltas[0].replace_snapshot is True
    assert deltas[0].final_sequence == 42
    assert deltas[0].asks[0].size == 5.0

    _, trades = parser.parse(
        {
            "channel": "push.deal",
            "symbol": "BTC_USDT",
            "ts": 1_700_000_000_001,
            "data": [{"p": 100.05, "v": 2, "T": 1, "t": 1_700_000_000_001, "i": 99}],
        },
        monotonic_ns(),
    )
    assert trades[0].side == "buy"
    assert trades[0].size == 2


def test_mexc_futures_subscriptions_use_contract_symbol():
    config = AppConfig.model_validate(
        {
            **AppConfig().model_dump(),
            "trading": {**AppConfig().trading.model_dump(), "market_type": "swap", "symbol": "BTC/USDT"},
        }
    )
    parser = NativeFeedParser(config)
    assert parser.url() == "wss://contract.mexc.com/edge"
    subs = parser.subscriptions()
    assert subs[0]["param"]["symbol"] == "BTC_USDT"


@pytest.mark.anyio
async def test_snapshot_replacement_sets_sequence_after_missing_rest_nonce():
    config = AppConfig()
    engine = MarketDataEngine()
    book = LocalOrderBook(depth=5)
    book.load_snapshot([[100.0, 2.0]], [[100.1, 2.0]], sequence=None)
    async with engine._lock:
        engine._book = book

    await engine._apply_book_deltas(
        config,
        [
            BookDelta(
                bids=[OrderBookLevel(100.0, 2.0)],
                asks=[OrderBookLevel(100.1, 2.0)],
                first_sequence=10,
                final_sequence=10,
                previous_sequence=None,
                event_time_ms=None,
                received_monotonic_ns=monotonic_ns(),
                replace_snapshot=True,
            )
        ],
    )

    assert engine._book is not None
    assert engine._book.sequence == 10


@pytest.mark.anyio
async def test_market_data_health_blocks_until_tape_ready():
    config = AppConfig()
    engine = MarketDataEngine()
    book = LocalOrderBook(depth=5)
    book.load_snapshot([[100.0, 2.0]], [[100.1, 2.0]], sequence=1)
    async with engine._lock:
        engine._book = book
        engine._status = "OK"
        engine._reason = "websocket synchronized"
        engine._last_ws_monotonic_ns = monotonic_ns()
        engine._last_book_monotonic_ns = monotonic_ns()
        engine._last_book_event_at = datetime.now(UTC).isoformat()

    health = await engine.health(config)

    assert health["status"] == "UNHEALTHY"
    assert health["reason"] == "tape_not_ready"


@pytest.mark.anyio
async def test_market_data_health_blocks_without_sequence():
    config = AppConfig()
    engine = MarketDataEngine()
    book = LocalOrderBook(depth=5)
    book.load_snapshot([[100.0, 2.0]], [[100.1, 2.0]], sequence=None)
    async with engine._lock:
        engine._book = book
        engine._status = "OK"
        engine._reason = "websocket synchronized"
        engine._last_ws_monotonic_ns = monotonic_ns()
        engine._last_book_monotonic_ns = monotonic_ns()
        engine._last_trade_monotonic_ns = monotonic_ns()

    health = await engine.health(config)

    assert health["status"] == "UNHEALTHY"
    assert health["reason"] == "sequence_not_available"


@pytest.mark.anyio
async def test_trade_side_must_be_consistent_with_book():
    config = AppConfig()
    engine = MarketDataEngine()
    book = LocalOrderBook(depth=5)
    book.load_snapshot([[100.0, 2.0]], [[100.1, 2.0]], sequence=1)
    async with engine._lock:
        engine._book = book
        engine._status = "OK"
        engine._reason = "websocket synchronized"

    with pytest.raises(ValueError, match="aggressor side"):
        await engine._apply_trades(
            config,
            [
                TapeDelta(
                    trade_id="bad-1",
                    price=99.5,
                    size=1.0,
                    side="buy",
                    sequence=1,
                    event_time_ms=None,
                    received_monotonic_ns=monotonic_ns(),
                )
            ],
        )


@pytest.mark.anyio
async def test_dom_delta_payload_contains_contract_fields():
    config = AppConfig()
    engine = MarketDataEngine()
    book = LocalOrderBook(depth=5)
    book.load_snapshot([[100.0, 2.0]], [[100.1, 2.0]], sequence=1)
    async with engine._lock:
        engine._book = book
        engine._status = "OK"
        engine._reason = "websocket synchronized"

    captured: list[dict] = []
    engine.subscribe_orderbook_updates(lambda payload: captured.append(payload))
    await engine._apply_book_deltas(
        config,
        [
            BookDelta(
                bids=[OrderBookLevel(100.0, 3.0)],
                asks=[OrderBookLevel(100.1, 1.5)],
                first_sequence=2,
                final_sequence=2,
                previous_sequence=1,
                event_time_ms=int(datetime.now(UTC).timestamp() * 1000),
                received_monotonic_ns=monotonic_ns(),
            )
        ],
    )
    assert captured
    dom_delta = captured[-1]["dom_delta"]
    assert dom_delta["type"] == "dom_delta"
    assert "updated_bids" in dom_delta
    assert "updated_asks" in dom_delta
    assert "book_health" in dom_delta


@pytest.mark.anyio
async def test_health_payload_exposes_observability_fields():
    config = AppConfig()
    engine = MarketDataEngine()
    book = LocalOrderBook(depth=5)
    book.load_snapshot([[100.0, 2.0]], [[100.1, 2.0]], sequence=1)
    async with engine._lock:
        engine._book = book
        engine._status = "OK"
        engine._reason = "websocket synchronized"
        engine._last_ws_monotonic_ns = monotonic_ns()
        engine._last_book_monotonic_ns = monotonic_ns()
        engine._last_trade_monotonic_ns = monotonic_ns()
    health = await engine.health(config, persist=False)
    assert "dom_queue_depth" in health
    assert "tape_queue_depth" in health
    assert "resync_count" in health
    assert "tick_to_render_p95" in health
