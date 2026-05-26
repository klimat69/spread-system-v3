from datetime import UTC, datetime

from app.config import AppConfig
from app.database import Trade, TradeRepository
from app.risk import RiskEngine
from app.strategy import MarketSnapshot, StrategyEngine


def test_strategy_blocks_when_edge_does_not_clear_fees():
    config = AppConfig()
    engine = StrategyEngine()
    snapshot = MarketSnapshot(bid=100.0, ask=100.05, bid_size=10, ask_size=10, liquidity=10_000)
    decision = engine.evaluate(snapshot, config)
    assert decision.should_trade is False
    assert decision.reason == "edge_below_minimum"


def test_strategy_allows_fee_aware_edge_when_filters_pass():
    config = AppConfig.model_validate({**AppConfig().model_dump(), "fees": {"maker": 0.0001, "taker": 0.0001}, "strategy": {"min_edge": 0.0005, "volatility_threshold": 0.05, "imbalance_limit": 0.9, "min_liquidity": 100.0, "volatility_window": 20}})
    engine = StrategyEngine()
    snapshot = MarketSnapshot(bid=100.0, ask=101.0, bid_size=10, ask_size=12, liquidity=10_000)
    decision = engine.evaluate(snapshot, config)
    assert decision.should_trade is True
    assert decision.edge > config.strategy.min_edge


def test_risk_blocks_daily_loss(tmp_path):
    repo = TradeRepository(tmp_path / "trades.sqlite")
    repo.insert_trade(Trade(timestamp=datetime.now(UTC).isoformat(), symbol="BTC/USDT", side="buy", price=100, size=1, pnl=-101, fee=0, exchange="binance"))
    risk = RiskEngine(repo)
    decision = risk.check(AppConfig(), "buy", 100, 0.001)
    assert decision.allowed is False
    assert decision.reason == "max_daily_loss_exceeded"
