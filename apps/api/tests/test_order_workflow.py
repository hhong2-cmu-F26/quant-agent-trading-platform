import asyncio
import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.agent_os import AgentOS
from trading_platform_api.broker import MockRobinhoodGateway
from trading_platform_api.models import Agent, AgentRole, OrderProposalCreate, OrderSide, OrderType
from trading_platform_api.orders import OrderWorkflow
from trading_platform_api.risk import RiskEngine
from trading_platform_api.store import InMemoryStore


def build_workflow() -> tuple[AgentOS, OrderWorkflow, InMemoryStore]:
    store = InMemoryStore()
    agent_os = AgentOS(store)
    workflow = OrderWorkflow(store, RiskEngine(), MockRobinhoodGateway())
    return agent_os, workflow, store


def test_order_flow_requires_risk_before_broker_review():
    agent_os, workflow, _ = build_workflow()
    agent = agent_os.register_agent(Agent(name="exec-agent-test", role=AgentRole.EXECUTION))
    proposal = workflow.create_proposal(
        OrderProposalCreate(
            agent_id=agent.id,
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=100,
            rationale="test proposal",
        )
    )

    with pytest.raises(ValueError, match="risk approved"):
        asyncio.run(workflow.broker_review(proposal.id))

    reviewed = workflow.risk_review(proposal.id)
    assert reviewed.status == "risk_approved"


def test_full_order_flow_reaches_submitted_with_mock_broker():
    agent_os, workflow, _ = build_workflow()
    agent = agent_os.register_agent(Agent(name="exec-agent-full", role=AgentRole.EXECUTION))
    proposal = workflow.create_proposal(
        OrderProposalCreate(
            agent_id=agent.id,
            symbol="MSFT",
            side=OrderSide.BUY,
            quantity=2,
            order_type=OrderType.LIMIT,
            limit_price=100,
            rationale="test proposal",
        )
    )

    workflow.risk_review(proposal.id)
    asyncio.run(workflow.broker_review(proposal.id))
    workflow.approve_for_execution(proposal.id)
    submitted = asyncio.run(workflow.submit(proposal.id))

    assert submitted.status == "submitted"
    assert submitted.execution is not None
    assert submitted.execution.broker_order_id.startswith("mock_")


def test_risk_rejects_missing_limit_price():
    agent_os, workflow, _ = build_workflow()
    agent = agent_os.register_agent(Agent(name="risk-agent-test", role=AgentRole.RISK))
    proposal = workflow.create_proposal(
        OrderProposalCreate(
            agent_id=agent.id,
            symbol="TSLA",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            rationale="market order should be blocked in v1",
        )
    )

    reviewed = workflow.risk_review(proposal.id)

    assert reviewed.status == "risk_rejected"
    assert reviewed.risk is not None
    assert "limit price is required" in reviewed.risk.reasons
