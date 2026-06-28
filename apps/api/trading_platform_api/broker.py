from __future__ import annotations

from abc import ABC, abstractmethod

from .models import BrokerReview, ExecutionReceipt, OrderProposal


class BrokerGateway(ABC):
    @abstractmethod
    async def review_equity_order(self, proposal: OrderProposal) -> BrokerReview:
        raise NotImplementedError

    @abstractmethod
    async def place_equity_order(self, proposal: OrderProposal) -> ExecutionReceipt:
        raise NotImplementedError


class MockRobinhoodGateway(BrokerGateway):
    """Development adapter with Robinhood-like review/place boundaries."""

    async def review_equity_order(self, proposal: OrderProposal) -> BrokerReview:
        estimated_notional = None
        warnings: list[str] = []
        if proposal.limit_price is not None:
            estimated_notional = proposal.limit_price * proposal.quantity
        if proposal.symbol.upper() in {"GME", "AMC"}:
            warnings.append("high volatility symbol")
        return BrokerReview(
            approved=True,
            warnings=warnings,
            estimated_notional=estimated_notional,
            raw={"adapter": "mock_robinhood"},
        )

    async def place_equity_order(self, proposal: OrderProposal) -> ExecutionReceipt:
        return ExecutionReceipt(
            broker_order_id=f"mock_{proposal.id}",
            status="submitted",
            raw={"adapter": "mock_robinhood"},
        )

