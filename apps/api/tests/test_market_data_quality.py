import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.market_data import DataQualityChecker, PriceBar


def bars(symbol="AAPL", count=5):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        PriceBar(
            symbol=symbol,
            timestamp=start + timedelta(days=index),
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100 + index,
            volume=1_000,
        )
        for index in range(count)
    ]


def issue_codes(report):
    return {issue.code for issue in report.issues}


def test_quality_checker_passes_clean_bars():
    report = DataQualityChecker().check(bars(), expected_symbol="AAPL")

    assert report.passed is True
    assert report.issue_count == 0
    assert report.bar_count == 5


def test_quality_checker_flags_bad_prices_and_duplicate_timestamps():
    bad = bars()
    bad.append(bad[-1].model_copy())
    bad[1] = bad[1].model_copy(update={"high": 90, "low": 100})
    bad[2] = bad[2].model_copy(update={"close": -1})

    report = DataQualityChecker().check(bad, expected_symbol="AAPL")

    assert report.passed is False
    assert "duplicate_timestamp" in issue_codes(report)
    assert "high_below_low" in issue_codes(report)
    assert "non_positive_price" in issue_codes(report)


def test_quality_checker_flags_gaps_and_stale_data():
    gapped = [bars()[0], bars()[1], bars()[4]]
    report = DataQualityChecker().check(
        gapped,
        expected_symbol="AAPL",
        max_staleness=timedelta(days=1),
        as_of=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    assert report.passed is True
    assert "missing_interval" in issue_codes(report)
    assert "stale_data" in issue_codes(report)

