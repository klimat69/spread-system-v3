from datetime import UTC, datetime, timedelta

import pytest

from app.config import AppConfig
from app import engine as engine_module
from app.database import Fill, OrderIntent, Position, ReconciliationEvent, TradeRepository
from app.ledger import PositionLedger
from app.reconciliation import ReconciliationService
from app.risk import RiskEngine


def test_order_can_be_traced_from_intent_to_partial_to_filled(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    intent = OrderIntent("binance", "spot", "BTC/USDT", "buy", "market", 1.0, None, "client-1")

    order = repo.create_order(intent)
    sent = repo.update_order(order["id"], status="SENT", exchange_order_id="ex-1")
    partial = repo.update_order(sent["id"], status="PARTIAL", filled_size=0.4, remaining_size=0.6)
    filled = repo.update_order(partial["id"], status="FILLED", filled_size=1.0, remaining_size=0.0, average_price=100.0)

    assert filled["client_order_id"] == "client-1"
    assert filled["exchange_order_id"] == "ex-1"
    assert filled["status"] == "FILLED"
    assert filled["filled_size"] == 1.0


def test_duplicate_exchange_trade_does_not_double_count_pnl(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    fill = Fill("binance", "spot", "BTC/USDT", "ex-1", "trade-1", "buy", 100.0, 1.0, 0.1, "USDT", "taker", datetime.now(UTC).isoformat(), "{}")

    assert repo.upsert_fill(fill) is not None
    assert repo.upsert_fill(fill) is None

    fills = repo.list_fills()
    assert len(fills) == 1


def test_spot_pnl_uses_entry_exit_and_fees_only(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    config = AppConfig.model_validate(
        {**AppConfig().model_dump(), "trading": {**AppConfig().trading.model_dump(), "market_type": "spot"}}
    )
    repo.upsert_fill(Fill("mexc", "spot", "BTC/USDT", "buy-1", "t1", "buy", 100.0, 1.0, 1.0, "USDT", "taker", datetime.now(UTC).isoformat(), "{}"))
    repo.upsert_fill(Fill("mexc", "spot", "BTC/USDT", "sell-1", "t2", "sell", 110.0, 0.4, 1.0, "USDT", "taker", datetime.now(UTC).isoformat(), "{}"))

    result = PositionLedger(repo).rebuild_from_fills(config, mark_price=120.0)

    assert result.position["size"] == pytest.approx(0.6)
    assert result.position["realized_pnl"] == pytest.approx(4.0)
    assert result.position["unrealized_pnl"] == pytest.approx(12.0)
    assert result.pnl["fees"] == pytest.approx(2.0)


def test_exit_without_entry_marks_unreconciled(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    config = AppConfig.model_validate(
        {**AppConfig().model_dump(), "trading": {**AppConfig().trading.model_dump(), "market_type": "spot"}}
    )
    repo.upsert_fill(Fill("mexc", "spot", "BTC/USDT", "sell-1", "t1", "sell", 100.0, 1.0, 0.0, "USDT", "taker", datetime.now(UTC).isoformat(), "{}"))

    result = PositionLedger(repo).rebuild_from_fills(config, mark_price=100.0)

    assert result.unreconciled is True


def test_risk_blocks_on_reconciliation_drift(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    config = AppConfig()
    repo.insert_reconciliation_event(
        ReconciliationEvent(
            severity="CRITICAL",
            kind="balance_drift",
            message="drift",
            exchange="binance",
            market_type="spot",
            symbol="BTC/USDT",
        )
    )

    decision = RiskEngine(repo).check(config, "buy", 100.0, 0.001)

    assert decision.allowed is False
    assert decision.reason == "reconciliation_blocked"


def test_restart_restores_orders_positions_and_risk_state(tmp_path):
    db_path = tmp_path / "core.sqlite"
    repo = TradeRepository(db_path)
    order = repo.create_order(OrderIntent("binance", "spot", "BTC/USDT", "buy", "market", 1.0, None, "client-restart"))
    repo.update_order(order["id"], status="OPEN", exchange_order_id="ex-restart")
    repo.upsert_position(Position("binance", "spot", "BTC/USDT", "BTC", "USDT", 1.0, 100.0, 0.0, 0.0, 100.0, "exchange", datetime.now(UTC).isoformat()))
    repo.update_risk_state(datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat())

    restarted = TradeRepository(db_path)

    assert restarted.list_orders(status=["OPEN"])[0]["exchange_order_id"] == "ex-restart"
    assert restarted.list_positions(symbol="BTC/USDT")[0]["size"] == 1.0
    assert restarted.get_risk_state()["cooldown_until"] is not None


def test_daily_pnl_uses_daily_delta_not_cumulative_total(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    repo.insert_pnl_snapshot("binance", "spot", "BTC/USDT", realized_pnl=200, unrealized_pnl=0, fees=0, source="test")
    repo.insert_pnl_snapshot("binance", "spot", "BTC/USDT", realized_pnl=80, unrealized_pnl=0, fees=0, source="test")

    assert repo.daily_pnl() == pytest.approx(80)


def test_ledger_loss_sets_persistent_cooldown(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    config = AppConfig()
    repo.insert_pnl_snapshot("binance", "spot", "BTC/USDT", realized_pnl=10, unrealized_pnl=0, fees=0, source="test")
    repo.upsert_fill(Fill("binance", "spot", "BTC/USDT", "buy-1", "t1", "buy", 100.0, 1.0, 0.0, "USDT", "taker", datetime.now(UTC).isoformat(), "{}"))
    repo.upsert_fill(Fill("binance", "spot", "BTC/USDT", "sell-1", "t2", "sell", 90.0, 1.0, 0.0, "USDT", "taker", datetime.now(UTC).isoformat(), "{}"))

    PositionLedger(repo).rebuild_from_fills(config, mark_price=90.0)

    assert repo.get_risk_state()["cooldown_until"] is not None


def test_holding_time_uses_first_fill_of_current_position_leg(tmp_path, monkeypatch):
    repo = TradeRepository(tmp_path / "core.sqlite")
    old_time = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    new_time = datetime.now(UTC).isoformat()
    repo.upsert_fill(Fill("binance", "spot", "BTC/USDT", "ex-1", "t1", "buy", 100.0, 0.5, 0.0, "USDT", "taker", old_time, "{}"))
    repo.upsert_fill(Fill("binance", "spot", "BTC/USDT", "ex-1", "t2", "buy", 100.0, 0.5, 0.0, "USDT", "taker", new_time, "{}"))
    repo.upsert_position(Position("binance", "spot", "BTC/USDT", "BTC", "USDT", 1.0, 100.0, 0.0, 0.0, 100.0, "test", new_time))
    config = AppConfig.model_validate({**AppConfig().model_dump(), "strategy": {**AppConfig().strategy.model_dump(), "max_holding_seconds": 8.0}})
    monkeypatch.setattr(engine_module, "trade_repository", repo)

    opened_at = engine_module.TradingEngine()._current_position_opened_at("BTC/USDT")
    reason = engine_module.TradingEngine()._holding_time_exit_reason(config)

    assert opened_at is not None
    assert opened_at.isoformat() == old_time
    assert reason == "max_holding_time_elapsed"


def test_reconciliation_events_are_deduplicated(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    event = ReconciliationEvent("CRITICAL", "balance_drift", "drift", "binance", "spot", "BTC/USDT")

    repo.insert_reconciliation_event(event)
    repo.insert_reconciliation_event(event)

    assert len(repo.list_reconciliation_events(unresolved_only=True)) == 1


@pytest.mark.anyio
async def test_swap_sync_does_not_refresh_cooldown_from_cumulative_fees(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    config = AppConfig.model_validate({**AppConfig().model_dump(), "trading": {**AppConfig().trading.model_dump(), "market_type": "swap"}})
    repo.upsert_fill(Fill("binance", "swap", "BTC/USDT", "ex-1", "t1", "buy", 100.0, 1.0, 2.0, "USDT", "taker", datetime.now(UTC).isoformat(), "{}"))

    class Adapter:
        async def fetch_order_status(self, *_args):
            raise AssertionError("not used")

        async def fetch_open_orders(self, *_args):
            return []

        async def fetch_my_trades(self, *_args):
            return []

        async def fetch_order_book(self, *_args):
            raise RuntimeError("no mark")

        async def fetch_balances(self, *_args):
            return {}

        async def fetch_positions(self, *_args):
            return [
                {
                    "symbol": "BTC/USDT",
                    "contracts": 1,
                    "side": "long",
                    "entryPrice": 100,
                    "markPrice": 100,
                    "realizedPnl": 0,
                    "unrealizedPnl": 0,
                }
            ]

    await ReconciliationService(repo, Adapter(), PositionLedger(repo)).sync(config)  # type: ignore[arg-type]
    await ReconciliationService(repo, Adapter(), PositionLedger(repo)).sync(config)  # type: ignore[arg-type]

    assert repo.get_risk_state()["cooldown_until"] is None


@pytest.mark.anyio
async def test_swap_missing_exchange_position_is_ok_when_local_position_is_flat(tmp_path):
    repo = TradeRepository(tmp_path / "core.sqlite")
    config = AppConfig.model_validate({**AppConfig().model_dump(), "trading": {**AppConfig().trading.model_dump(), "market_type": "swap"}})

    class Adapter:
        async def fetch_open_orders(self, *_args):
            return []

        async def fetch_my_trades(self, *_args):
            return []

        async def fetch_order_book(self, *_args):
            raise RuntimeError("no mark")

        async def fetch_balances(self, *_args):
            return {}

        async def fetch_positions(self, *_args):
            return []

    result = await ReconciliationService(repo, Adapter(), PositionLedger(repo)).sync(config)  # type: ignore[arg-type]

    assert result["blocking"] is False


def test_paper_exit_price_closes_at_correct_book_side():
    from app.engine import paper_exit_price

    bid, ask = 99.5, 100.5
    assert paper_exit_price("buy", bid, ask) == bid
    assert paper_exit_price("sell", bid, ask) == ask


def test_paper_book_sane_rejects_wide_spread():
    from app.engine import paper_book_sane
    from app.market_state import MarketState

    ok = MarketState(best_bid=100.0, best_ask=100.2)
    assert paper_book_sane(ok) is True

    bad = MarketState(best_bid=71208.0, best_ask=73410.0)
    assert paper_book_sane(bad) is False


def test_account_balance_asset_amount():
    from app.account_balance import _asset_amount

    balances = {"free": {"USDT": 12.5}, "total": {"USDT": 20.0}}
    assert _asset_amount(balances, "USDT", "free") == 12.5
    assert _asset_amount(balances, "USDT", "total") == 20.0
    assert _asset_amount(balances, "BTC", "free") == 0.0
