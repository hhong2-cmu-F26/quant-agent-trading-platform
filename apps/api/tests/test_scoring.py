import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.models import BacktestRecord
from trading_platform_api.scoring import StrategyScorer, StrategyScoringConfig


def record(strategy_id, symbol, return_pct, max_drawdown_pct=0.0, trade_count=2, rejected_trade_count=0):
    return BacktestRecord(
        strategy_id=strategy_id,
        symbol=symbol,
        metrics={
            "return_pct": return_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "trade_count": trade_count,
            "rejected_trade_count": rejected_trade_count,
        },
    )


def test_strategy_scorer_ranks_by_risk_adjusted_score():
    scorer = StrategyScorer()
    high_return_high_drawdown = record("fast_momentum", "AAPL", return_pct=12.0, max_drawdown_pct=8.0)
    steady = record("steady_momentum", "AAPL", return_pct=9.0, max_drawdown_pct=1.0)

    scores = scorer.score([high_return_high_drawdown, steady])

    assert scores[0].strategy_id == "steady_momentum"
    assert scores[0].rank == 1
    assert scores[0].score == 8.0
    assert scores[1].rank == 2


def test_strategy_scorer_penalizes_rejections_and_low_trade_count():
    scorer = StrategyScorer(StrategyScoringConfig(min_trades=2))
    clean = record("clean", "MSFT", return_pct=3.0, trade_count=2)
    noisy = record("noisy", "MSFT", return_pct=5.0, trade_count=0, rejected_trade_count=1)

    scores = scorer.score([noisy, clean])

    assert scores[0].strategy_id == "clean"
    assert "insufficient_trade_count" in scores[1].reasons
    assert "rejected_trade_penalty:2.00" in scores[1].reasons
