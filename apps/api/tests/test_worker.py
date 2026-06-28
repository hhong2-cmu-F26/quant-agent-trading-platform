import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.agent_os import AgentOS
from trading_platform_api.backtest import MomentumBacktestConfig, MomentumBacktestEngine, backtest_record_from_result
from trading_platform_api.broker import MockRobinhoodGateway
from trading_platform_api.execution_policy import ExecutionPolicy, ExecutionPolicyConfig
from trading_platform_api.market_data import PriceBar
from trading_platform_api.models import AccountState, Agent, AgentRole, AgentTask, PortfolioPosition
from trading_platform_api.orders import OrderWorkflow
from trading_platform_api.risk import RiskEngine
from trading_platform_api.store import InMemoryStore
from trading_platform_api.worker import build_default_worker


def bar_payload():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "symbol": "AAPL",
            "timestamp": (start + timedelta(days=index)).isoformat(),
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100 + index,
            "volume": 1_000_000,
        }
        for index in range(30)
    ]


def build_worker_context():
    store = InMemoryStore()
    agent_os = AgentOS(store)
    broker = MockRobinhoodGateway(
        account=AccountState(buying_power=25_000, cash=20_000, equity=30_000),
        positions=[PortfolioPosition(symbol="AAPL", quantity=2, average_price=150)],
    )
    workflow = OrderWorkflow(
        store,
        RiskEngine(),
        broker,
        ExecutionPolicy(ExecutionPolicyConfig(allow_auto_submit=True)),
    )
    worker = build_default_worker(store, workflow)
    return store, agent_os, worker


def test_worker_processes_momentum_task_and_creates_order_proposal():
    store, agent_os, worker = build_worker_context()
    agent = agent_os.register_agent(Agent(name="quant-worker-agent", role=AgentRole.QUANT_RESEARCH))
    task = agent_os.create_task(
        AgentTask(
            agent_id=agent.id,
            kind="quant.momentum_proposal",
            payload={
                "bars": bar_payload(),
                "lookback": 20,
                "min_momentum": 0.01,
                "target_notional": 1_000,
            },
        )
    )

    summary = worker.run_once()
    completed = store.get_task(task.id)

    assert summary.processed == 1
    assert summary.succeeded == 1
    assert completed.status == "completed"
    assert completed.result["proposal_created"] is True
    assert store.get_proposal(completed.result["proposal_id"]) is not None


def test_worker_marks_unknown_task_kind_failed():
    store, agent_os, worker = build_worker_context()
    agent = agent_os.register_agent(Agent(name="bad-task-agent", role=AgentRole.MONITORING))
    task = agent_os.create_task(AgentTask(agent_id=agent.id, kind="unknown.kind"))

    summary = worker.run_once()
    failed = store.get_task(task.id)

    assert summary.failed == 1
    assert failed.status == "failed"
    assert "no handler registered" in failed.error


def test_worker_can_create_momentum_proposal_from_stored_bars():
    store, agent_os, worker = build_worker_context()
    store.save_price_bars([PriceBar.model_validate(item) for item in bar_payload()])
    agent = agent_os.register_agent(Agent(name="stored-bars-agent", role=AgentRole.QUANT_RESEARCH))
    task = agent_os.create_task(
        AgentTask(
            agent_id=agent.id,
            kind="quant.momentum_proposal",
            payload={
                "symbol": "AAPL",
                "lookback": 20,
                "min_momentum": 0.01,
                "target_notional": 1_000,
            },
        )
    )

    summary = worker.run_once()
    completed = store.get_task(task.id)

    assert summary.succeeded == 1
    assert completed.result["proposal_created"] is True
    assert store.get_proposal(completed.result["proposal_id"]).symbol == "AAPL"


def test_worker_can_run_market_data_quality_check():
    store, agent_os, worker = build_worker_context()
    store.save_price_bars([PriceBar.model_validate(item) for item in bar_payload()])
    agent = agent_os.register_agent(Agent(name="quality-agent", role=AgentRole.DATA_QUALITY))
    task = agent_os.create_task(
        AgentTask(
            agent_id=agent.id,
            kind="market_data.quality_check",
            payload={"symbol": "AAPL", "limit": 30},
        )
    )

    summary = worker.run_once()
    completed = store.get_task(task.id)

    assert summary.succeeded == 1
    assert completed.status == "completed"
    assert completed.result["passed"] is True
    assert completed.result["symbol"] == "AAPL"


def test_worker_can_run_momentum_backtest_from_stored_bars():
    store, agent_os, worker = build_worker_context()
    store.save_price_bars([PriceBar.model_validate(item) for item in bar_payload()])
    agent = agent_os.register_agent(Agent(name="backtest-agent", role=AgentRole.BACKTEST))
    task = agent_os.create_task(
        AgentTask(
            agent_id=agent.id,
            kind="backtest.momentum",
            payload={
                "symbol": "AAPL",
                "lookback": 20,
                "min_momentum": 0.01,
                "target_notional": 1_000,
            },
        )
    )

    summary = worker.run_once()
    completed = store.get_task(task.id)

    assert summary.succeeded == 1
    assert completed.status == "completed"
    assert completed.result["record"]["symbol"] == "AAPL"
    assert completed.result["result"]["metrics"]["trade_count"] == 2
    assert store.get_backtest(completed.result["backtest_id"]) is not None


def test_worker_can_rank_persisted_backtests():
    store, agent_os, worker = build_worker_context()
    config = MomentumBacktestConfig(lookback=20, min_momentum=0.01, target_notional=1_000)
    result = MomentumBacktestEngine(config).run([PriceBar.model_validate(item) for item in bar_payload()])
    store.save_backtest(backtest_record_from_result(result, config))
    agent = agent_os.register_agent(Agent(name="scoring-agent", role=AgentRole.QUANT_RESEARCH))
    task = agent_os.create_task(
        AgentTask(
            agent_id=agent.id,
            kind="strategy.score_backtests",
            payload={"symbol": "AAPL", "limit": 10},
        )
    )

    summary = worker.run_once()
    completed = store.get_task(task.id)

    assert summary.succeeded == 1
    assert completed.status == "completed"
    assert completed.result["score_count"] == 1
    assert completed.result["scores"][0]["rank"] == 1
    assert completed.result["scores"][0]["symbol"] == "AAPL"


def test_worker_can_sync_portfolio_from_broker():
    store, agent_os, worker = build_worker_context()
    agent = agent_os.register_agent(Agent(name="portfolio-agent", role=AgentRole.MONITORING))
    task = agent_os.create_task(AgentTask(agent_id=agent.id, kind="portfolio.sync"))

    summary = worker.run_once()
    completed = store.get_task(task.id)

    assert summary.succeeded == 1
    assert completed.status == "completed"
    assert completed.result["account"]["buying_power"] == 25_000
    assert completed.result["position_count"] == 1
    assert store.get_position("AAPL").quantity == 2


def test_worker_can_fetch_broker_quotes():
    store, agent_os, worker = build_worker_context()
    agent = agent_os.register_agent(Agent(name="quote-agent", role=AgentRole.MARKET_RESEARCH))
    task = agent_os.create_task(
        AgentTask(
            agent_id=agent.id,
            kind="market_data.quote_snapshot",
            payload={"symbols": ["aapl", "msft"]},
        )
    )

    summary = worker.run_once()
    completed = store.get_task(task.id)

    assert summary.succeeded == 1
    assert completed.status == "completed"
    assert completed.result["quote_count"] == 2
    assert completed.result["quotes"][0]["symbol"] == "AAPL"


def test_worker_can_check_broker_tradability():
    store, agent_os, worker = build_worker_context()
    agent = agent_os.register_agent(Agent(name="tradability-agent", role=AgentRole.RISK))
    task = agent_os.create_task(
        AgentTask(
            agent_id=agent.id,
            kind="market_data.tradability_check",
            payload={"symbols": ["aapl", "zzzz"]},
        )
    )

    summary = worker.run_once()
    completed = store.get_task(task.id)

    assert summary.succeeded == 1
    assert completed.status == "completed"
    assert completed.result["tradability_count"] == 2
    assert completed.result["tradability"][0]["state"] == "tradable"
    assert completed.result["tradability"][1]["state"] == "not_tradable"
