import asyncio
import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.agent_os import AgentOS
from trading_platform_api.broker import MockRobinhoodGateway
from trading_platform_api.execution_policy import ExecutionPolicy, ExecutionPolicyConfig
from trading_platform_api.models import (
    Agent,
    AgentRole,
    BrokerOrderSnapshot,
    BrokerOrderStatus,
    OrderProposalCreate,
    OrderSide,
    OrderType,
)
from trading_platform_api.orders import OrderWorkflow
from trading_platform_api.reconciliation import ReconciliationService
from trading_platform_api.risk import RiskEngine
from trading_platform_api.sqlite_store import SQLiteStore
from trading_platform_api.store import InMemoryStore


def build_submitted_buy(store, symbol="AAPL", quantity=10, price=100):
    agent_os = AgentOS(store)
    agent = agent_os.register_agent(Agent(name=f"agent-{symbol}", role=AgentRole.EXECUTION))
    workflow = OrderWorkflow(
        store,
        RiskEngine(),
        MockRobinhoodGateway(),
        ExecutionPolicy(ExecutionPolicyConfig(allow_auto_submit=True)),
    )
    proposal = workflow.create_proposal(
        OrderProposalCreate(
            agent_id=agent.id,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=price,
            rationale="reconciliation test",
        )
    )
    workflow.risk_review(proposal.id)
    asyncio.run(workflow.broker_review(proposal.id))
    workflow.approve_for_execution(proposal.id)
    return asyncio.run(workflow.submit(proposal.id))


def test_reconcile_partial_then_final_fill_updates_position_incrementally():
    store = InMemoryStore()
    submitted = build_submitted_buy(store)
    service = ReconciliationService(store)

    partial = service.reconcile_order(
        BrokerOrderSnapshot(
            broker_order_id=submitted.execution.broker_order_id,
            proposal_id=submitted.id,
            symbol="aapl",
            side=OrderSide.BUY,
            status=BrokerOrderStatus.PARTIALLY_FILLED,
            submitted_quantity=10,
            filled_quantity=4,
            average_fill_price=101,
        )
    )
    position = store.get_position("AAPL")

    assert partial.status == "submitted"
    assert position.quantity == 4
    assert position.average_price == 101

    final = service.reconcile_order(
        BrokerOrderSnapshot(
            broker_order_id=submitted.execution.broker_order_id,
            proposal_id=submitted.id,
            symbol="AAPL",
            side=OrderSide.BUY,
            status=BrokerOrderStatus.FILLED,
            submitted_quantity=10,
            filled_quantity=10,
            average_fill_price=102,
        )
    )
    position = store.get_position("AAPL")

    assert final.status == "filled"
    assert position.quantity == 10
    assert position.average_price == pytest.approx(101.6)


def test_reconcile_rejects_decreasing_fill_quantity():
    store = InMemoryStore()
    submitted = build_submitted_buy(store)
    service = ReconciliationService(store)
    service.reconcile_order(
        BrokerOrderSnapshot(
            broker_order_id=submitted.execution.broker_order_id,
            proposal_id=submitted.id,
            symbol="AAPL",
            side=OrderSide.BUY,
            status=BrokerOrderStatus.PARTIALLY_FILLED,
            submitted_quantity=10,
            filled_quantity=5,
            average_fill_price=100,
        )
    )

    with pytest.raises(ValueError, match="filled quantity cannot decrease"):
        service.reconcile_order(
            BrokerOrderSnapshot(
                broker_order_id=submitted.execution.broker_order_id,
                proposal_id=submitted.id,
                symbol="AAPL",
                side=OrderSide.BUY,
                status=BrokerOrderStatus.PARTIALLY_FILLED,
                submitted_quantity=10,
                filled_quantity=4,
                average_fill_price=100,
            )
        )


def test_reconciled_position_persists_in_sqlite(tmp_path):
    store = SQLiteStore(tmp_path / "platform.db")
    submitted = build_submitted_buy(store, symbol="MSFT", quantity=3, price=200)
    service = ReconciliationService(store)
    service.reconcile_order(
        BrokerOrderSnapshot(
            broker_order_id=submitted.execution.broker_order_id,
            proposal_id=submitted.id,
            symbol="MSFT",
            side=OrderSide.BUY,
            status=BrokerOrderStatus.FILLED,
            submitted_quantity=3,
            filled_quantity=3,
            average_fill_price=201,
        )
    )

    reloaded = SQLiteStore(tmp_path / "platform.db")
    position = reloaded.get_position("msft")
    proposal = reloaded.get_proposal(submitted.id)

    assert position.quantity == 3
    assert position.average_price == 201
    assert proposal.status == "filled"

