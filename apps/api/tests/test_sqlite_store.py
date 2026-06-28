import asyncio
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.agent_os import AgentOS
from trading_platform_api.broker import MockRobinhoodGateway
from trading_platform_api.execution_policy import ExecutionPolicy, ExecutionPolicyConfig
from trading_platform_api.models import Agent, AgentMessage, AgentRole, AgentTask, OrderProposalCreate, OrderSide, OrderType
from trading_platform_api.orders import OrderWorkflow
from trading_platform_api.risk import RiskEngine
from trading_platform_api.sqlite_store import SQLiteStore


def test_sqlite_store_persists_agents_messages_and_heartbeat_state(tmp_path):
    db_path = tmp_path / "platform.db"
    store = SQLiteStore(db_path)
    agent_os = AgentOS(store)
    agent = agent_os.register_agent(Agent(name="persistent-agent", role=AgentRole.MONITORING))
    agent_os.create_task(AgentTask(agent_id=agent.id, kind="portfolio_sync"))
    message = agent_os.send_message(AgentMessage(agent_id=agent.id, kind="notice", content="check orders"))

    reloaded = SQLiteStore(db_path)
    reloaded_os = AgentOS(reloaded)
    heartbeat = reloaded_os.heartbeat(agent.id)

    assert len(heartbeat["tasks"]) == 1
    assert len(heartbeat["messages"]) == 1
    assert reloaded.get_message(message.id).read is True


def test_sqlite_store_persists_order_workflow_state(tmp_path):
    db_path = tmp_path / "platform.db"
    store = SQLiteStore(db_path)
    agent_os = AgentOS(store)
    agent = agent_os.register_agent(Agent(name="persistent-exec", role=AgentRole.EXECUTION))
    workflow = OrderWorkflow(
        store,
        RiskEngine(),
        MockRobinhoodGateway(),
        ExecutionPolicy(ExecutionPolicyConfig(allow_auto_submit=True)),
    )
    proposal = workflow.create_proposal(
        OrderProposalCreate(
            agent_id=agent.id,
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=100,
            rationale="persistence test",
        )
    )

    workflow.risk_review(proposal.id)
    asyncio.run(workflow.broker_review(proposal.id))
    workflow.approve_for_execution(proposal.id)
    asyncio.run(workflow.submit(proposal.id))

    reloaded = SQLiteStore(db_path)
    persisted = reloaded.get_proposal(proposal.id)

    assert persisted.status == "submitted"
    assert persisted.execution is not None
    assert persisted.execution.broker_order_id.startswith("mock_")


def test_sqlite_store_persists_audit_events(tmp_path):
    db_path = tmp_path / "platform.db"
    store = SQLiteStore(db_path)
    agent_os = AgentOS(store)
    agent = agent_os.register_agent(Agent(name="audit-agent", role=AgentRole.RISK))

    reloaded = SQLiteStore(db_path)
    events = reloaded.list_audit_events()

    assert events[0]["event_type"] == "agent_registered"
    assert events[0]["payload"]["agent_id"] == agent.id
