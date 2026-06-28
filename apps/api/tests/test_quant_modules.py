import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.market_data import FeatureEngine, PriceBar
from trading_platform_api.models import OrderSide
from trading_platform_api.paper import PaperTrade, PaperTradingEngine
from trading_platform_api.strategy import MomentumStrategy, MomentumStrategyConfig


def bars(symbol: str = "AAPL") -> list[PriceBar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        PriceBar(
            symbol=symbol,
            timestamp=start + timedelta(days=index),
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100 + index,
            volume=1_000_000,
        )
        for index in range(30)
    ]


def test_feature_engine_builds_momentum_snapshot():
    snapshot = FeatureEngine().build_snapshot(bars(), lookback=20)

    assert snapshot.symbol == "AAPL"
    assert snapshot.observations == 20
    assert snapshot.momentum > 0
    assert snapshot.realized_volatility >= 0


def test_momentum_strategy_creates_limit_buy_proposal():
    snapshot = FeatureEngine().build_snapshot(bars(), lookback=20)
    strategy = MomentumStrategy(MomentumStrategyConfig(min_momentum=0.01, target_notional=1_000))

    proposal = strategy.propose("agent_1", snapshot)

    assert proposal is not None
    assert proposal.symbol == "AAPL"
    assert proposal.side == OrderSide.BUY
    assert proposal.limit_price is not None
    assert proposal.quantity > 0


def test_paper_engine_replays_long_only_trades_and_scores():
    engine = PaperTradingEngine()
    trades = [
        PaperTrade(symbol="AAPL", side=OrderSide.BUY, quantity=10, price=100),
        PaperTrade(symbol="AAPL", side=OrderSide.SELL, quantity=5, price=110),
    ]

    portfolio, metrics = engine.replay(trades, marks={"AAPL": 120})

    assert portfolio.cash == 99_550
    assert portfolio.positions["AAPL"].quantity == 5
    assert metrics.ending_equity == 100_150
    assert metrics.return_pct > 0
    assert metrics.trade_count == 2

