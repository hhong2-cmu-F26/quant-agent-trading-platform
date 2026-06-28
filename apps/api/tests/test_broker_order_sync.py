import asyncio
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.agent_os import AgentOS
from trading_platform_api.broker import MockRobinhoodGateway
from trading_platform_api.broker_order_sync import BrokerOrderSyncService
from trading_platform_api.execution_policy import ExecutionPolicy, ExecutionPolicyConfig
from trading_platform_api.models import Agent, AgentRole, BrokerOrderSnapshot, BrokerOrderStatus, OrderProposalCreate, OrderSide, OrderType
from trading_platform_api.orders import OrderWorkflow
from trading_platform_api.risk import RiskEngine
from trading_platform_api.store import InMemoryStore


def test_broker_order_sync_reconciles_submitted_fill():
    store = InMemoryStore()
    agent_os = AgentOS(store)
    broker = MockRobinhoodGateway()
    workflow = OrderWorkflow(
        store,
        RiskEngine(),
        broker,
        ExecutionPolicy(ExecutionPolicyConfig(allow_auto_submit=True)),
    )
    agent = agent_os.register_agent(Agent(name="sync-agent", role=AgentRole.EXECUTION))
    proposal = workflow.create_proposal(
        OrderProposalCreate(
            agent_id=agent.id,
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=2,
            order_type=OrderType.LIMIT,
            limit_price=100,
        )
    )
    workflow.risk_review(proposal.id)
    asyncio.run(workflow.broker_review(proposal.id))
    workflow.approve_for_execution(proposal.id)
    submitted = asyncio.run(workflow.submit(proposal.id))
    broker.order_snapshots[submitted.execution.broker_order_id] = BrokerOrderSnapshot(
        broker_order_id=submitted.execution.broker_order_id,
        proposal_id=submitted.id,
        symbol="AAPL",
        side=OrderSide.BUY,
        status=BrokerOrderStatus.FILLED,
        submitted_quantity=2,
        filled_quantity=2,
        average_fill_price=101.25,
    )

    result = asyncio.run(BrokerOrderSyncService(store, broker).sync_submitted())

    assert result["checked"] == 1
    assert result["reconciled"] == 1
    assert store.get_proposal(proposal.id).status == "filled"
    assert store.get_position("AAPL").quantity == 2
    assert store.get_position("AAPL").average_price == 101.25
