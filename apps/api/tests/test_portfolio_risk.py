import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.agent_os import AgentOS
from trading_platform_api.models import AccountState, Agent, AgentRole, OrderProposalCreate, OrderSide, OrderType, PortfolioPosition
from trading_platform_api.orders import OrderWorkflow
from trading_platform_api.broker import MockRobinhoodGateway
from trading_platform_api.execution_policy import ExecutionPolicy, ExecutionPolicyConfig
from trading_platform_api.risk import PortfolioRiskEngine, RiskLimits
from trading_platform_api.sqlite_store import SQLiteStore
from trading_platform_api.store import InMemoryStore


def build_workflow(store, limits=None):
    return OrderWorkflow(
        store,
        PortfolioRiskEngine(store, limits=limits),
        MockRobinhoodGateway(),
        ExecutionPolicy(ExecutionPolicyConfig(allow_auto_submit=True)),
    )


def test_portfolio_risk_blocks_buy_above_buying_power():
    store = InMemoryStore()
    store.save_account_state(AccountState(buying_power=50, cash=50, equity=1_000))
    agent = AgentOS(store).register_agent(Agent(name="risk-buying-power", role=AgentRole.RISK))
    proposal = build_workflow(store).create_proposal(
        OrderProposalCreate(
            agent_id=agent.id,
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=100,
        )
    )

    reviewed = build_workflow(store).risk_review(proposal.id)

    assert reviewed.status == "risk_rejected"
    assert "buy notional exceeds buying power" in reviewed.risk.reasons


def test_portfolio_risk_blocks_projected_symbol_concentration():
    store = InMemoryStore()
    store.save_account_state(AccountState(buying_power=10_000, cash=10_000, equity=10_000))
    store.save_position(PortfolioPosition(symbol="AAPL", quantity=40, average_price=100))
    agent = AgentOS(store).register_agent(Agent(name="risk-concentration", role=AgentRole.RISK))
    workflow = build_workflow(store, RiskLimits(max_symbol_position_notional=4_500, max_symbol_equity_pct=100))
    proposal = workflow.create_proposal(
        OrderProposalCreate(
            agent_id=agent.id,
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            limit_price=100,
        )
    )

    reviewed = workflow.risk_review(proposal.id)

    assert reviewed.status == "risk_rejected"
    assert "projected symbol notional exceeds concentration limit" in reviewed.risk.reasons
    assert reviewed.risk.checks["projected_symbol_notional"] == 5_000


def test_account_state_persists_in_sqlite(tmp_path):
    store = SQLiteStore(tmp_path / "platform.db")
    store.save_account_state(AccountState(buying_power=123, cash=100, equity=456))

    reloaded = SQLiteStore(tmp_path / "platform.db")
    account = reloaded.get_account_state()

    assert account.buying_power == 123
    assert account.cash == 100
    assert account.equity == 456

