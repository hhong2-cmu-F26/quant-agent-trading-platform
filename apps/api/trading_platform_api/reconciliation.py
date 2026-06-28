from __future__ import annotations

from math import isfinite

from .models import (
    BrokerOrderSnapshot,
    BrokerOrderStatus,
    OrderSide,
    PortfolioPosition,
    ProposalStatus,
    utc_now,
)
from .store import Repository


class ReconciliationService:
    """Apply broker-observed order truth to proposals and positions."""

    def __init__(self, store: Repository):
        self.store = store

    def reconcile_order(self, snapshot: BrokerOrderSnapshot):
        proposal = self.store.get_proposal(snapshot.proposal_id)
        if not proposal:
            raise ValueError("proposal not found")
        if proposal.execution and proposal.execution.broker_order_id != snapshot.broker_order_id:
            raise ValueError("broker order id does not match proposal execution")

        normalized = self._normalize_snapshot(snapshot)
        previous = self.store.get_broker_order(normalized.broker_order_id)
        incremental_fill = normalized.filled_quantity
        if previous:
            incremental_fill -= previous.filled_quantity
        if incremental_fill < -1e-12:
            raise ValueError("filled quantity cannot decrease")

        self.store.save_broker_order(normalized)
        if incremental_fill > 1e-12 and normalized.average_fill_price is not None:
            self._apply_fill(normalized, incremental_fill)

        proposal.status = self._proposal_status(normalized.status)
        proposal.updated_at = utc_now()
        self.store.save_proposal(proposal)
        self.store.audit(
            "order_reconciled",
            proposal_id=proposal.id,
            broker_order_id=normalized.broker_order_id,
            broker_status=normalized.status,
            filled_quantity=normalized.filled_quantity,
            incremental_fill=incremental_fill,
        )
        return proposal

    def _normalize_snapshot(self, snapshot: BrokerOrderSnapshot) -> BrokerOrderSnapshot:
        symbol = snapshot.symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        if snapshot.submitted_quantity <= 0 or not isfinite(snapshot.submitted_quantity):
            raise ValueError("submitted quantity must be positive")
        if snapshot.filled_quantity < 0 or not isfinite(snapshot.filled_quantity):
            raise ValueError("filled quantity must be non-negative")
        if snapshot.filled_quantity > snapshot.submitted_quantity + 1e-12:
            raise ValueError("filled quantity exceeds submitted quantity")
        if snapshot.filled_quantity > 0 and (snapshot.average_fill_price is None or snapshot.average_fill_price <= 0):
            raise ValueError("average fill price is required for fills")
        snapshot.symbol = symbol
        return snapshot

    def _apply_fill(self, snapshot: BrokerOrderSnapshot, incremental_fill: float) -> None:
        price = float(snapshot.average_fill_price or 0)
        current = self.store.get_position(snapshot.symbol)
        if snapshot.side == OrderSide.BUY:
            if current:
                new_quantity = current.quantity + incremental_fill
                current.average_price = (
                    ((current.quantity * current.average_price) + (incremental_fill * price)) / new_quantity
                    if new_quantity > 0
                    else 0.0
                )
                current.quantity = new_quantity
                current.updated_at = utc_now()
                self.store.save_position(current)
                return
            self.store.save_position(
                PortfolioPosition(symbol=snapshot.symbol, quantity=incremental_fill, average_price=price)
            )
            return

        if snapshot.side == OrderSide.SELL:
            if not current or current.quantity < incremental_fill - 1e-12:
                raise ValueError("sell fill exceeds current position")
            current.quantity -= incremental_fill
            current.updated_at = utc_now()
            if current.quantity <= 1e-12:
                current.quantity = 0.0
            self.store.save_position(current)
            return

        raise ValueError(f"unsupported side: {snapshot.side}")

    def _proposal_status(self, status: BrokerOrderStatus) -> ProposalStatus:
        if status == BrokerOrderStatus.FILLED:
            return ProposalStatus.FILLED
        if status == BrokerOrderStatus.CANCELLED:
            return ProposalStatus.CANCELLED
        if status in {BrokerOrderStatus.REJECTED, BrokerOrderStatus.FAILED}:
            return ProposalStatus.FAILED
        return ProposalStatus.SUBMITTED

