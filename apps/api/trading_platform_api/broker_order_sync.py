from __future__ import annotations

from .broker import BrokerGateway
from .models import ProposalStatus
from .reconciliation import ReconciliationService
from .store import Repository


class BrokerOrderSyncService:
    """Polls broker order truth for submitted proposals and reconciles fills."""

    def __init__(self, store: Repository, broker: BrokerGateway):
        self.store = store
        self.broker = broker
        self.reconciliation = ReconciliationService(store)

    async def sync_submitted(self, limit: int = 50) -> dict:
        proposals = self.store.list_proposals(status=ProposalStatus.SUBMITTED.value, limit=limit)
        reconciled = []
        skipped = []
        for proposal in proposals:
            if not proposal.execution:
                skipped.append({"proposal_id": proposal.id, "reason": "missing execution receipt"})
                continue
            snapshot = await self.broker.get_equity_order(proposal)
            updated = self.reconciliation.reconcile_order(snapshot)
            reconciled.append(
                {
                    "proposal_id": updated.id,
                    "broker_order_id": snapshot.broker_order_id,
                    "broker_status": snapshot.status.value,
                    "filled_quantity": snapshot.filled_quantity,
                }
            )

        self.store.audit(
            "broker_orders_synced",
            checked=len(proposals),
            reconciled=len(reconciled),
            skipped=len(skipped),
        )
        return {
            "checked": len(proposals),
            "reconciled": len(reconciled),
            "skipped": skipped,
            "orders": reconciled,
        }
