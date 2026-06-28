from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agent_os import AgentOS
from .broker import MockRobinhoodGateway
from .execution_policy import ExecutionPolicy, ExecutionPolicyConfig
from .market_data import FeatureEngine, PriceBar
from .models import Agent, AgentMessage, AgentTask, OrderProposalCreate
from .orders import OrderWorkflow
from .paper import PaperTrade, PaperTradingEngine
from .risk import RiskEngine
from .sqlite_store import SQLiteStore
from .strategy import MomentumStrategy, MomentumStrategyConfig


app = FastAPI(title="Quant Agent Trading Platform API")

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "trading_platform.db"
repository = SQLiteStore(os.getenv("TRADING_PLATFORM_DB_PATH", str(DEFAULT_DB_PATH)))
agent_os = AgentOS(repository)
order_workflow = OrderWorkflow(
    repository,
    RiskEngine(),
    MockRobinhoodGateway(),
    ExecutionPolicy(ExecutionPolicyConfig(allow_auto_submit=True)),
)
feature_engine = FeatureEngine()
paper_engine = PaperTradingEngine()


class FeatureRequest(BaseModel):
    bars: list[PriceBar]
    lookback: int = 20


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


@app.post("/agents/tasks", response_model=AgentTask)
async def create_task(task: AgentTask) -> AgentTask:
    try:
        return agent_os.create_task(task)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.post("/agents/messages", response_model=AgentMessage)
async def send_message(message: AgentMessage) -> AgentMessage:
    try:
        return agent_os.send_message(message)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.post("/agents/{agent_id}/heartbeat")
async def heartbeat(agent_id: str) -> dict:
    try:
        return agent_os.heartbeat(agent_id)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.post("/orders/proposals")
async def create_order_proposal(request: OrderProposalCreate):
    try:
        return order_workflow.create_proposal(request)
    except ValueError as exc:
        raise bad_request(exc) from exc


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


@app.post("/quant/features")
async def build_features(request: FeatureRequest):
    try:
        return feature_engine.build_snapshot(request.bars, lookback=request.lookback)
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


@app.post("/paper/replay")
async def replay_paper_trades(request: PaperReplayRequest):
    portfolio, metrics = paper_engine.replay(request.trades, marks=request.marks)
    return {"portfolio": portfolio, "metrics": metrics}
