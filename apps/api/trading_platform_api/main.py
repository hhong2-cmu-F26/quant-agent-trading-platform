from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .agent_os import AgentOS
from .broker import MockRobinhoodGateway
from .models import Agent, AgentMessage, AgentTask, OrderProposalCreate
from .orders import OrderWorkflow
from .risk import RiskEngine
from .store import store


app = FastAPI(title="Quant Agent Trading Platform API")

agent_os = AgentOS(store)
order_workflow = OrderWorkflow(store, RiskEngine(), MockRobinhoodGateway())


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


@app.post("/orders/proposals/{proposal_id}/submit")
async def submit(proposal_id: str):
    try:
        return await order_workflow.submit(proposal_id)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/audit")
async def audit_log() -> dict:
    return {"events": store.audit_events}

