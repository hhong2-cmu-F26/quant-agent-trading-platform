from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agent_os import AgentOS
from .backtest import MomentumBacktestConfig, MomentumBacktestEngine, backtest_record_from_result
from .broker import MockRobinhoodGateway
from .execution_policy import ExecutionPolicy, ExecutionPolicyConfig
from .market_data import DataQualityChecker, FeatureEngine, PriceBar
from .models import AccountState, Agent, AgentMessage, AgentTask, BrokerOrderSnapshot, OrderProposalCreate
from .orders import OrderWorkflow
from .paper import PaperTrade, PaperTradingEngine
from .reconciliation import ReconciliationService
from .risk import PortfolioRiskEngine
from .scoring import StrategyScorer, StrategyScoringConfig
from .sqlite_store import SQLiteStore
from .strategy import MomentumStrategy, MomentumStrategyConfig
from .worker import build_default_worker


app = FastAPI(title="Quant Agent Trading Platform API")

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "trading_platform.db"
repository = SQLiteStore(os.getenv("TRADING_PLATFORM_DB_PATH", str(DEFAULT_DB_PATH)))
agent_os = AgentOS(repository)
order_workflow = OrderWorkflow(
    repository,
    PortfolioRiskEngine(repository),
    MockRobinhoodGateway(),
    ExecutionPolicy(ExecutionPolicyConfig(allow_auto_submit=True)),
)
feature_engine = FeatureEngine()
quality_checker = DataQualityChecker()
paper_engine = PaperTradingEngine()
reconciliation_service = ReconciliationService(repository)
task_worker = build_default_worker(repository, order_workflow)


class FeatureRequest(BaseModel):
    bars: list[PriceBar]
    lookback: int = 20


class StoredFeatureRequest(BaseModel):
    symbol: str
    lookback: int = 20
    limit: int = 200


class StoredQualityRequest(BaseModel):
    symbol: str
    limit: int = 200
    max_staleness_seconds: int | None = None


class MomentumProposalRequest(BaseModel):
    agent_id: str
    bars: list[PriceBar]
    lookback: int = 20
    min_momentum: float = 0.03
    max_volatility: float = 0.60
    target_notional: float = 500.0


class PaperReplayRequest(BaseModel):
    trades: list[PaperTrade]
    marks: dict[str, float] = Field(default_factory=dict)


class PriceBarsRequest(BaseModel):
    bars: list[PriceBar]


class MomentumBacktestRequest(BaseModel):
    bars: list[PriceBar]
    lookback: int = 20
    min_momentum: float = 0.03
    max_volatility: float = 0.60
    target_notional: float = 500.0
    starting_cash: float = 100_000.0


class StoredMomentumBacktestRequest(BaseModel):
    symbol: str
    limit: int = 500
    lookback: int = 20
    min_momentum: float = 0.03
    max_volatility: float = 0.60
    target_notional: float = 500.0
    starting_cash: float = 100_000.0


class StrategyScoringRequest(BaseModel):
    symbol: str | None = None
    limit: int = 50
    min_trades: int = 1
    drawdown_weight: float = 1.0
    rejected_trade_penalty: float = 2.0
    low_trade_penalty: float = 5.0


def bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/agents", response_model=Agent)
async def register_agent(agent: Agent) -> Agent:
    try:
        return agent_os.register_agent(agent)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/agents")
async def list_agents() -> dict:
    return {"agents": repository.list_agents()}


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = repository.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


@app.post("/agents/tasks", response_model=AgentTask)
async def create_task(task: AgentTask) -> AgentTask:
    try:
        return agent_os.create_task(task)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/agents/tasks")
async def list_tasks(status: str | None = None, limit: int = 50) -> dict:
    return {"tasks": repository.list_tasks(status=status, limit=limit)}


@app.get("/agents/tasks/{task_id}")
async def get_task(task_id: str):
    task = repository.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.post("/agents/messages", response_model=AgentMessage)
async def send_message(message: AgentMessage) -> AgentMessage:
    try:
        return agent_os.send_message(message)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/agents/messages")
async def list_messages(unread_only: bool = False, limit: int = 50) -> dict:
    return {"messages": repository.list_messages(unread_only=unread_only, limit=limit)}


@app.post("/agents/{agent_id}/heartbeat")
async def heartbeat(agent_id: str) -> dict:
    try:
        return agent_os.heartbeat(agent_id)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/agents/{agent_id}/tasks")
async def list_agent_tasks(agent_id: str, status: str | None = None, limit: int = 50) -> dict:
    if not repository.get_agent(agent_id):
        raise HTTPException(status_code=404, detail="agent not found")
    return {"tasks": repository.list_tasks_for_agent(agent_id, status=status, limit=limit)}


@app.get("/agents/{agent_id}/messages")
async def list_agent_messages(agent_id: str, unread_only: bool = False, limit: int = 50) -> dict:
    if not repository.get_agent(agent_id):
        raise HTTPException(status_code=404, detail="agent not found")
    return {"messages": repository.list_messages_for_agent(agent_id, unread_only=unread_only, limit=limit)}


@app.post("/worker/run-once")
async def run_worker_once(limit: int = 10):
    return task_worker.run_once(limit=limit)


@app.post("/orders/proposals")
async def create_order_proposal(request: OrderProposalCreate):
    try:
        return order_workflow.create_proposal(request)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/orders/proposals")
async def list_order_proposals(status: str | None = None, limit: int = 50) -> dict:
    return {"proposals": repository.list_proposals(status=status, limit=limit)}


@app.get("/orders/proposals/{proposal_id}")
async def get_order_proposal(proposal_id: str):
    proposal = repository.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal not found")
    return proposal


@app.post("/orders/proposals/{proposal_id}/risk-review")
async def risk_review(proposal_id: str):
    try:
        return order_workflow.risk_review(proposal_id)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.post("/orders/proposals/{proposal_id}/broker-review")
async def broker_review(proposal_id: str):
    try:
        return await order_workflow.broker_review(proposal_id)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.post("/orders/proposals/{proposal_id}/approve")
async def approve(proposal_id: str):
    try:
        return order_workflow.approve_for_execution(proposal_id)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.post("/orders/proposals/{proposal_id}/policy-review")
async def policy_review(proposal_id: str):
    try:
        return order_workflow.policy_review(proposal_id)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.post("/orders/proposals/{proposal_id}/submit")
async def submit(proposal_id: str):
    try:
        return await order_workflow.submit(proposal_id)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/audit")
async def audit_log() -> dict:
    return {"events": repository.list_audit_events()}


@app.post("/orders/reconcile")
async def reconcile_order(snapshot: BrokerOrderSnapshot):
    try:
        return reconciliation_service.reconcile_order(snapshot)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/portfolio/positions")
async def list_positions() -> dict:
    return {"positions": repository.list_positions()}


@app.get("/account")
async def get_account() -> dict:
    return {"account": repository.get_account_state()}


@app.put("/account")
async def update_account(account: AccountState):
    return repository.save_account_state(account)


@app.get("/broker/orders")
async def list_broker_orders(limit: int = 50) -> dict:
    return {"broker_orders": repository.list_broker_orders(limit=limit)}


@app.get("/dashboard/summary")
async def dashboard_summary() -> dict:
    pending_tasks = repository.list_tasks(status="pending", limit=1_000)
    running_tasks = repository.list_tasks(status="running", limit=1_000)
    proposals = repository.list_proposals(limit=1_000)
    positions = repository.list_positions()
    return {
        "account": repository.get_account_state(),
        "agent_count": len(repository.list_agents()),
        "pending_task_count": len(pending_tasks),
        "running_task_count": len(running_tasks),
        "proposal_count": len(proposals),
        "backtest_count": len(repository.list_backtests(limit=1_000)),
        "open_position_count": len([position for position in positions if abs(position.quantity) > 1e-12]),
        "recent_proposals": proposals[:10],
        "positions": positions,
    }


@app.post("/market-data/bars")
async def save_price_bars(request: PriceBarsRequest):
    bars = repository.save_price_bars(request.bars)
    if bars:
        repository.audit(
            "market_data_bars_saved",
            symbol=bars[-1].symbol,
            count=len(bars),
            latest_timestamp=bars[-1].timestamp,
        )
    return {"bars": bars, "count": len(bars)}


@app.get("/market-data/bars/{symbol}")
async def list_price_bars(symbol: str, limit: int = 200):
    return {"bars": repository.list_price_bars(symbol, limit=limit)}


@app.post("/market-data/quality")
async def check_market_data_quality(request: StoredQualityRequest):
    bars = repository.list_price_bars(request.symbol, limit=request.limit)
    max_staleness = None
    if request.max_staleness_seconds is not None:
        from datetime import timedelta

        max_staleness = timedelta(seconds=request.max_staleness_seconds)
    return quality_checker.check(
        bars,
        expected_symbol=request.symbol,
        max_staleness=max_staleness,
    )


@app.post("/quant/features")
async def build_features(request: FeatureRequest):
    try:
        return feature_engine.build_snapshot(request.bars, lookback=request.lookback)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.post("/quant/features/from-store")
async def build_stored_features(request: StoredFeatureRequest):
    bars = repository.list_price_bars(request.symbol, limit=request.limit)
    try:
        return feature_engine.build_snapshot(bars, lookback=request.lookback)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.post("/quant/momentum/proposal")
async def build_momentum_proposal(request: MomentumProposalRequest):
    try:
        features = feature_engine.build_snapshot(request.bars, lookback=request.lookback)
    except ValueError as exc:
        raise bad_request(exc) from exc

    strategy = MomentumStrategy(
        MomentumStrategyConfig(
            min_momentum=request.min_momentum,
            max_volatility=request.max_volatility,
            target_notional=request.target_notional,
        )
    )
    proposal = strategy.propose(request.agent_id, features)
    return {"features": features, "proposal": proposal}


@app.post("/quant/momentum/proposal/from-store")
async def build_stored_momentum_proposal(request: StoredFeatureRequest, agent_id: str):
    bars = repository.list_price_bars(request.symbol, limit=request.limit)
    try:
        features = feature_engine.build_snapshot(bars, lookback=request.lookback)
    except ValueError as exc:
        raise bad_request(exc) from exc

    proposal = MomentumStrategy().propose(agent_id, features)
    return {"features": features, "proposal": proposal}


@app.post("/paper/replay")
async def replay_paper_trades(request: PaperReplayRequest):
    portfolio, metrics = paper_engine.replay(request.trades, marks=request.marks)
    return {"portfolio": portfolio, "metrics": metrics}


@app.post("/backtests/momentum")
async def run_momentum_backtest(request: MomentumBacktestRequest):
    config = MomentumBacktestConfig(
        lookback=request.lookback,
        min_momentum=request.min_momentum,
        max_volatility=request.max_volatility,
        target_notional=request.target_notional,
        starting_cash=request.starting_cash,
    )
    engine = MomentumBacktestEngine(config)
    try:
        result = engine.run(request.bars)
    except ValueError as exc:
        raise bad_request(exc) from exc
    record = repository.save_backtest(backtest_record_from_result(result, config))
    repository.audit("backtest_recorded", backtest_id=record.id, symbol=record.symbol, strategy_id=record.strategy_id)
    return {"record": record, "result": result}


@app.post("/backtests/momentum/from-store")
async def run_stored_momentum_backtest(request: StoredMomentumBacktestRequest):
    bars = repository.list_price_bars(request.symbol, limit=request.limit)
    config = MomentumBacktestConfig(
        lookback=request.lookback,
        min_momentum=request.min_momentum,
        max_volatility=request.max_volatility,
        target_notional=request.target_notional,
        starting_cash=request.starting_cash,
    )
    engine = MomentumBacktestEngine(config)
    try:
        result = engine.run(bars)
    except ValueError as exc:
        raise bad_request(exc) from exc
    record = repository.save_backtest(backtest_record_from_result(result, config))
    repository.audit("backtest_recorded", backtest_id=record.id, symbol=record.symbol, strategy_id=record.strategy_id)
    return {"record": record, "result": result}


@app.get("/backtests")
async def list_backtests(symbol: str | None = None, limit: int = 50) -> dict:
    return {"backtests": repository.list_backtests(symbol=symbol, limit=limit)}


@app.post("/backtests/scores")
async def score_backtests(request: StrategyScoringRequest):
    records = repository.list_backtests(symbol=request.symbol, limit=request.limit)
    scorer = StrategyScorer(
        StrategyScoringConfig(
            min_trades=request.min_trades,
            drawdown_weight=request.drawdown_weight,
            rejected_trade_penalty=request.rejected_trade_penalty,
            low_trade_penalty=request.low_trade_penalty,
        )
    )
    return {"scores": scorer.score(records)}


@app.get("/backtests/{backtest_id}")
async def get_backtest(backtest_id: str):
    record = repository.get_backtest(backtest_id)
    if not record:
        raise HTTPException(status_code=404, detail="backtest not found")
    return record
