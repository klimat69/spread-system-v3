from datetime import UTC, datetime

from app.config import AppConfig
from app.database import Position, TradeRepository
from app.risk import RiskEngine
from app.strategy import MarketSnapshot, OrderBookLevel, StrategyEngine, TapePrint


def _trade(side: str, price: float, size: float) -> TapePrint:
    return TapePrint(price=price, size=size, side=side, timestamp=datetime.now(UTC).isoformat())


def test_strategy_blocks_without_real_tape_flow():
    config = AppConfig()
    engine = StrategyEngine()
    snapshot = MarketSnapshot(
        bid=100.0,
        ask=100.05,
        bid_size=10,
        ask_size=10,
        liquidity=10_000,
        timestamp=datetime.now(UTC).isoformat(),
        bids=[OrderBookLevel(100.0, 10), OrderBookLevel(99.9, 10), OrderBookLevel(99.8, 10)],
        asks=[OrderBookLevel(100.05, 10), OrderBookLevel(100.1, 10), OrderBookLevel(100.2, 10)],
        recent_trades=[],
    )
    decision = engine.evaluate(snapshot, config)
    assert decision.should_trade is False
    assert decision.reason == "tape_insufficient"


def test_strategy_allows_orderflow_microscalp_when_dom_and_tape_align():
    config = AppConfig.model_validate(
        {
            **AppConfig().model_dump(),
            "strategy": {
                **AppConfig().strategy.model_dump(),
                "volatility_threshold": 0.05,
                "imbalance_limit": 0.25,
                "min_liquidity": 100.0,
                "min_tape_notional": 100.0,
                "momentum_burst_multiplier": 1.0,
                "min_wall_notional": 100.0,
            },
        }
    )
    engine = StrategyEngine()
    snapshot = MarketSnapshot(
        bid=100.0,
        ask=100.05,
        bid_size=80,
        ask_size=10,
        liquidity=20_000,
        timestamp=datetime.now(UTC).isoformat(),
        bids=[OrderBookLevel(100.0, 120), OrderBookLevel(99.95, 8), OrderBookLevel(99.9, 8), OrderBookLevel(99.85, 8)],
        asks=[OrderBookLevel(100.05, 10), OrderBookLevel(100.1, 8), OrderBookLevel(100.15, 8), OrderBookLevel(100.2, 8)],
        recent_trades=[_trade("buy", 100.05, 5), _trade("buy", 100.06, 4), _trade("sell", 100.0, 0.5)],
    )
    decision = engine.evaluate(snapshot, config)
    assert decision.should_trade is True
    assert decision.side == "buy"
    assert decision.entry_reason == "bid_pressure_buy_aggression_momentum"
    assert decision.edge == 0.0


def test_strategy_fast_exit_when_orderflow_weakens():
    config = AppConfig.model_validate(
        {
            **AppConfig().model_dump(),
            "strategy": {
                **AppConfig().strategy.model_dump(),
                "imbalance_limit": 0.25,
                "min_liquidity": 100.0,
                "min_tape_notional": 10.0,
                "momentum_burst_multiplier": 1.0,
                "min_wall_notional": 100.0,
            },
        }
    )
    engine = StrategyEngine()
    entry_snapshot = MarketSnapshot(
        bid=100.0,
        ask=100.05,
        bid_size=80,
        ask_size=10,
        liquidity=20_000,
        timestamp=datetime.now(UTC).isoformat(),
        bids=[OrderBookLevel(100.0, 120), OrderBookLevel(99.95, 8), OrderBookLevel(99.9, 8)],
        asks=[OrderBookLevel(100.05, 10), OrderBookLevel(100.1, 8), OrderBookLevel(100.15, 8)],
        recent_trades=[_trade("buy", 100.05, 5), _trade("buy", 100.06, 4)],
    )
    engine.evaluate(entry_snapshot, config)
    weak_snapshot = MarketSnapshot(
        bid=100.0,
        ask=100.05,
        bid_size=12,
        ask_size=10,
        liquidity=6_000,
        timestamp=datetime.now(UTC).isoformat(),
        bids=[OrderBookLevel(100.0, 12), OrderBookLevel(99.95, 8), OrderBookLevel(99.9, 8)],
        asks=[OrderBookLevel(100.05, 10), OrderBookLevel(100.1, 8), OrderBookLevel(100.15, 8)],
        recent_trades=[_trade("sell", 100.0, 3), _trade("sell", 99.99, 3)],
    )
    decision = engine.evaluate(weak_snapshot, config)
    assert decision.should_exit is True
    assert decision.exit_reason in {"imbalance_weakening", "opposite_sell_aggression", "bid_liquidity_wall_removed"}


def test_risk_blocks_daily_loss(tmp_path):
    repo = TradeRepository(tmp_path / "trades.sqlite")
    repo.insert_pnl_snapshot("binance", "spot", "BTC/USDT", realized_pnl=-101, unrealized_pnl=0, fees=0, source="test")
    risk = RiskEngine(repo)
    decision = risk.check(AppConfig(), "buy", 100, 0.001)
    assert decision.allowed is False
    assert decision.reason == "max_daily_loss_exceeded"


def test_risk_loads_inventory_from_trade_history(tmp_path):
    repo = TradeRepository(tmp_path / "trades.sqlite")
    repo.upsert_position(
        Position(
            exchange="binance",
            market_type="spot",
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            size=1.5,
            average_entry_price=100,
            realized_pnl=0,
            unrealized_pnl=0,
            mark_price=100,
            source="test",
            last_synced_at=datetime.now(UTC).isoformat(),
        )
    )

    risk = RiskEngine(repo)

    assert risk.inventory == 1.5
