import asyncio
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.agent_os import AgentOS
from trading_platform_api.backtest import MomentumBacktestConfig, MomentumBacktestEngine, backtest_record_from_result
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


def test_sqlite_store_lists_proposals_and_messages(tmp_path):
    db_path = tmp_path / "platform.db"
    store = SQLiteStore(db_path)
    agent_os = AgentOS(store)
    agent = agent_os.register_agent(Agent(name="query-persist-agent", role=AgentRole.MONITORING))
    message = agent_os.send_message(AgentMessage(agent_id=agent.id, kind="notice", content="hello"))
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
        )
    )

    reloaded = SQLiteStore(db_path)

    assert reloaded.list_messages()[0].id == message.id
    assert reloaded.list_proposals()[0].id == proposal.id


def test_sqlite_store_persists_backtest_records(tmp_path):
    from datetime import datetime, timedelta, timezone

    from trading_platform_api.market_data import PriceBar

    bars = [
        PriceBar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100 + index,
            volume=1_000_000,
        )
        for index in range(40)
    ]
    config = MomentumBacktestConfig(lookback=20, min_momentum=0.01, target_notional=1_000)
    result = MomentumBacktestEngine(config).run(bars)
    store = SQLiteStore(tmp_path / "platform.db")
    record = store.save_backtest(backtest_record_from_result(result, config))

    reloaded = SQLiteStore(tmp_path / "platform.db")

    assert reloaded.get_backtest(record.id).metrics["trade_count"] == 2
    assert reloaded.list_backtests(symbol="AAPL")[0].id == record.id
