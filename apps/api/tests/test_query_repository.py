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
from trading_platform_api.store import InMemoryStore


def test_repository_query_methods_return_current_dashboard_state():
    store = InMemoryStore()
    agent_os = AgentOS(store)
    workflow = OrderWorkflow(
        store,
        RiskEngine(),
        MockRobinhoodGateway(),
        ExecutionPolicy(ExecutionPolicyConfig(allow_auto_submit=True)),
    )
    agent = agent_os.register_agent(Agent(name="query-agent", role=AgentRole.QUANT_RESEARCH))
    task = agent_os.create_task(AgentTask(agent_id=agent.id, kind="quant.momentum_proposal"))
    message = agent_os.send_message(AgentMessage(agent_id=agent.id, kind="notice", content="hello"))
    proposal = workflow.create_proposal(
        OrderProposalCreate(
            agent_id=agent.id,
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=100,
        )
    )

    assert store.list_agents()[0].id == agent.id
    assert store.list_tasks(status="pending")[0].id == task.id
    assert store.list_messages(unread_only=True)[0].id == message.id
    assert store.list_proposals()[0].id == proposal.id

