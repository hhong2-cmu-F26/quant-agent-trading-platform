import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.market_data import FeatureEngine, PriceBar
from trading_platform_api.sqlite_store import SQLiteStore
from trading_platform_api.store import InMemoryStore


def bars(symbol="AAPL", count=30):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        PriceBar(
            symbol=symbol.lower(),
            timestamp=start + timedelta(days=index),
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100 + index,
            volume=1_000_000,
        )
        for index in range(count)
    ]


def test_in_memory_store_saves_and_lists_normalized_bars():
    store = InMemoryStore()
    saved = store.save_price_bars(bars())

    listed = store.list_price_bars("aapl", limit=5)

    assert saved[-1].symbol == "AAPL"
    assert len(listed) == 5
    assert listed[-1].close == 129


def test_sqlite_store_persists_price_bars(tmp_path):
    store = SQLiteStore(tmp_path / "platform.db")
    store.save_price_bars(bars("MSFT"))

    reloaded = SQLiteStore(tmp_path / "platform.db")
    listed = reloaded.list_price_bars("msft", limit=30)
    snapshot = FeatureEngine().build_snapshot(listed, lookback=20)

    assert len(listed) == 30
    assert listed[0].symbol == "MSFT"
    assert snapshot.symbol == "MSFT"
    assert snapshot.momentum > 0

