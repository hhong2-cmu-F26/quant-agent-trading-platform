from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class AgentRole(str, Enum):
    USER_COPILOT = "user_copilot"
    MARKET_RESEARCH = "market_research"
    DATA_QUALITY = "data_quality"
    QUANT_RESEARCH = "quant_research"
    BACKTEST = "backtest"
    RISK = "risk"
    EXECUTION = "execution"
    MONITORING = "monitoring"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    RISK_APPROVED = "risk_approved"
    RISK_REJECTED = "risk_rejected"
    BROKER_REVIEWED = "broker_reviewed"
    APPROVED_FOR_EXECUTION = "approved_for_execution"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Agent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("agent"))
    name: str
    role: AgentRole
    created_at: datetime = Field(default_factory=utc_now)


class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: new_id("task"))
    agent_id: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    created_at: datetime = Field(default_factory=utc_now)
    read_at: datetime | None = None


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    agent_id: str
    kind: str
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)
    read: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class OrderProposalCreate(BaseModel):
    agent_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.LIMIT
    limit_price: float | None = None
    rationale: str = ""
    strategy_id: str | None = None


class RiskDecision(BaseModel):
    approved: bool
    reasons: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)


class BrokerReview(BaseModel):
    approved: bool
    warnings: list[str] = Field(default_factory=list)
    estimated_notional: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ExecutionReceipt(BaseModel):
    broker_order_id: str
    status: str
    raw: dict[str, Any] = Field(default_factory=dict)


class OrderProposal(BaseModel):
    id: str = Field(default_factory=lambda: new_id("proposal"))
    agent_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    limit_price: float | None = None
    rationale: str = ""
    strategy_id: str | None = None
    status: ProposalStatus = ProposalStatus.PROPOSED
    risk: RiskDecision | None = None
    broker_review: BrokerReview | None = None
    execution: ExecutionReceipt | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
