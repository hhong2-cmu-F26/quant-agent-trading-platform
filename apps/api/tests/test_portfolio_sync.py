import asyncio
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.broker import MockRobinhoodGateway
from trading_platform_api.models import AccountState, PortfolioPosition
from trading_platform_api.portfolio_sync import PortfolioSyncService
from trading_platform_api.store import InMemoryStore


def test_portfolio_sync_persists_broker_account_and_positions():
    store = InMemoryStore()
    broker = MockRobinhoodGateway(
        account=AccountState(buying_power=2_000, cash=1_500, equity=5_000),
        positions=[PortfolioPosition(symbol="aapl", quantity=3, average_price=100)],
    )
    service = PortfolioSyncService(store, broker)

    result = asyncio.run(service.sync())

    assert result["position_count"] == 1
    assert store.get_account_state().buying_power == 2_000
    assert store.get_position("AAPL").quantity == 3
    assert store.list_audit_events()[0]["event_type"] == "portfolio_synced"
