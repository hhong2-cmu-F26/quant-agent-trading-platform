import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.backtest import MomentumBacktestConfig, MomentumBacktestEngine, backtest_record_from_result
from trading_platform_api.market_data import PriceBar
from trading_platform_api.models import OrderSide


def bars(symbol="AAPL", count=40):
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
        for index in range(count)
    ]


def test_momentum_backtest_generates_entry_and_exit_trades():
    engine = MomentumBacktestEngine(
        MomentumBacktestConfig(
            lookback=20,
            min_momentum=0.01,
            target_notional=1_000,
        )
    )

    result = engine.run(bars())

    assert result.symbol == "AAPL"
    assert result.feature_count > 0
    assert result.signal_count == 1
    assert len(result.trades) == 2
    assert result.trades[0].side == OrderSide.BUY
    assert result.trades[1].side == OrderSide.SELL
    assert result.metrics.trade_count == 2


def test_momentum_backtest_rejects_insufficient_history():
    engine = MomentumBacktestEngine(MomentumBacktestConfig(lookback=20))

    try:
        engine.run(bars(count=10))
        raised = False
    except ValueError as exc:
        raised = "not enough bars" in str(exc)

    assert raised is True


def test_backtest_record_contains_metrics_and_result_payload():
    config = MomentumBacktestConfig(
        lookback=20,
        min_momentum=0.01,
        target_notional=1_000,
    )
    result = MomentumBacktestEngine(config).run(bars())

    record = backtest_record_from_result(result, config)

    assert record.strategy_id == "long_momentum_v1"
    assert record.symbol == "AAPL"
    assert record.metrics["trade_count"] == 2
    assert record.result["symbol"] == "AAPL"
