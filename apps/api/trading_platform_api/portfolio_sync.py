from __future__ import annotations

from .broker import BrokerGateway
from .store import Repository


class PortfolioSyncService:
    """Persists broker-observed account and position state."""

    def __init__(self, store: Repository, broker: BrokerGateway):
        self.store = store
        self.broker = broker

    async def sync(self) -> dict:
        account = await self.broker.get_account()
        positions = await self.broker.get_positions()
        saved_account = self.store.save_account_state(account)
        saved_positions = [self.store.save_position(position) for position in positions]
        self.store.audit(
            "portfolio_synced",
            buying_power=saved_account.buying_power,
            cash=saved_account.cash,
            equity=saved_account.equity,
            position_count=len(saved_positions),
        )
        return {
            "account": saved_account,
            "positions": saved_positions,
            "position_count": len(saved_positions),
        }
