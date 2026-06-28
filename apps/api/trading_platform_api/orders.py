from __future__ import annotations

from .broker import BrokerGateway
from .models import OrderProposal, OrderProposalCreate, ProposalStatus, utc_now
from .risk import RiskEngine
from .store import Repository


class OrderWorkflow:
    def __init__(self, store: Repository, risk: RiskEngine, broker: BrokerGateway):
        self.store = store
        self.risk = risk
        self.broker = broker

    def create_proposal(self, request: OrderProposalCreate) -> OrderProposal:
        if not self.store.get_agent(request.agent_id):
            raise ValueError("agent not found")
        proposal = OrderProposal(**request.model_dump())
        proposal.symbol = proposal.symbol.strip().upper()
        self.store.add_proposal(proposal)
        self.store.audit("order_proposed", proposal_id=proposal.id, agent_id=proposal.agent_id)
        return proposal

    def risk_review(self, proposal_id: str) -> OrderProposal:
        proposal = self._get(proposal_id)
        decision = self.risk.review(proposal)
        proposal.risk = decision
        proposal.status = ProposalStatus.RISK_APPROVED if decision.approved else ProposalStatus.RISK_REJECTED
        proposal.updated_at = utc_now()
        self.store.save_proposal(proposal)
        self.store.audit(
            "order_risk_reviewed",
            proposal_id=proposal.id,
            approved=decision.approved,
            reasons=decision.reasons,
        )
        return proposal

    async def broker_review(self, proposal_id: str) -> OrderProposal:
        proposal = self._get(proposal_id)
        if proposal.status != ProposalStatus.RISK_APPROVED:
            raise ValueError("proposal must be risk approved before broker review")
        review = await self.broker.review_equity_order(proposal)
        proposal.broker_review = review
        proposal.status = ProposalStatus.BROKER_REVIEWED
        proposal.updated_at = utc_now()
        self.store.save_proposal(proposal)
        self.store.audit(
            "order_broker_reviewed",
            proposal_id=proposal.id,
            approved=review.approved,
            warnings=review.warnings,
        )
        return proposal

    def approve_for_execution(self, proposal_id: str) -> OrderProposal:
        proposal = self._get(proposal_id)
        if proposal.status != ProposalStatus.BROKER_REVIEWED:
            raise ValueError("proposal must be broker reviewed before approval")
        if not proposal.broker_review or not proposal.broker_review.approved:
            raise ValueError("broker review did not approve proposal")
        proposal.status = ProposalStatus.APPROVED_FOR_EXECUTION
        proposal.updated_at = utc_now()
        self.store.save_proposal(proposal)
        self.store.audit("order_approved_for_execution", proposal_id=proposal.id)
        return proposal

    async def submit(self, proposal_id: str) -> OrderProposal:
        proposal = self._get(proposal_id)
        if proposal.status != ProposalStatus.APPROVED_FOR_EXECUTION:
            raise ValueError("proposal must be approved for execution")
        receipt = await self.broker.place_equity_order(proposal)
        proposal.execution = receipt
        proposal.status = ProposalStatus.SUBMITTED
        proposal.updated_at = utc_now()
        self.store.save_proposal(proposal)
        self.store.audit(
            "order_submitted",
            proposal_id=proposal.id,
            broker_order_id=receipt.broker_order_id,
            broker_status=receipt.status,
        )
        return proposal

    def _get(self, proposal_id: str) -> OrderProposal:
        proposal = self.store.get_proposal(proposal_id)
        if not proposal:
            raise ValueError("proposal not found")
        return proposal
