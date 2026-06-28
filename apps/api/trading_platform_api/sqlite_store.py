from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .market_data import PriceBar
from .models import AccountState, Agent, AgentMessage, AgentTask, BacktestRecord, BrokerOrderSnapshot, OrderProposal, PortfolioPosition, utc_now

ModelT = TypeVar("ModelT", bound=BaseModel)


class SQLiteStore:
    """Small durable repository for the early agent OS.

    The domain objects are stored as JSON documents. This keeps the first
    persistence layer flexible while the order/risk model is still evolving.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS objects (
                    kind TEXT NOT NULL,
                    id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (kind, id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_objects_kind ON objects(kind)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at)")

    def add_agent(self, agent: Agent) -> Agent:
        self._put("agent", agent.id, agent)
        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._get("agent", agent_id, Agent)

    def list_agents(self) -> list[Agent]:
        return self._list("agent", Agent)

    def add_task(self, task: AgentTask) -> AgentTask:
        self._put("task", task.id, task)
        return task

    def get_task(self, task_id: str) -> AgentTask | None:
        return self._get("task", task_id, AgentTask)

    def list_tasks(self, status: str | None = None, limit: int = 20) -> list[AgentTask]:
        tasks = self._list("task", AgentTask)
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        return sorted(tasks, key=lambda task: task.created_at)[:limit]

    def list_tasks_for_agent(self, agent_id: str, status: str | None = None, limit: int = 20) -> list[AgentTask]:
        tasks = [task for task in self._list("task", AgentTask) if task.agent_id == agent_id]
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        return sorted(tasks, key=lambda task: task.created_at)[:limit]

    def save_task(self, task: AgentTask) -> AgentTask:
        self._put("task", task.id, task)
        return task

    def add_message(self, message: AgentMessage) -> AgentMessage:
        self._put("message", message.id, message)
        return message

    def get_message(self, message_id: str) -> AgentMessage | None:
        return self._get("message", message_id, AgentMessage)

    def list_messages(self, unread_only: bool = False, limit: int = 20) -> list[AgentMessage]:
        messages = self._list("message", AgentMessage)
        if unread_only:
            messages = [message for message in messages if not message.read]
        return sorted(messages, key=lambda message: message.created_at)[:limit]

    def list_messages_for_agent(self, agent_id: str, unread_only: bool = False, limit: int = 20) -> list[AgentMessage]:
        messages = [message for message in self._list("message", AgentMessage) if message.agent_id == agent_id]
        if unread_only:
            messages = [message for message in messages if not message.read]
        return sorted(messages, key=lambda message: message.created_at)[:limit]

    def save_message(self, message: AgentMessage) -> AgentMessage:
        self._put("message", message.id, message)
        return message

    def add_proposal(self, proposal: OrderProposal) -> OrderProposal:
        self._put("proposal", proposal.id, proposal)
        return proposal

    def get_proposal(self, proposal_id: str) -> OrderProposal | None:
        return self._get("proposal", proposal_id, OrderProposal)

    def list_proposals(self, status: str | None = None, limit: int = 50) -> list[OrderProposal]:
        proposals = self._list("proposal", OrderProposal)
        if status is not None:
            proposals = [proposal for proposal in proposals if proposal.status == status]
        return sorted(proposals, key=lambda proposal: proposal.created_at, reverse=True)[:limit]

    def save_proposal(self, proposal: OrderProposal) -> OrderProposal:
        self._put("proposal", proposal.id, proposal)
        return proposal

    def save_broker_order(self, snapshot: BrokerOrderSnapshot) -> BrokerOrderSnapshot:
        self._put("broker_order", snapshot.broker_order_id, snapshot)
        return snapshot

    def get_broker_order(self, broker_order_id: str) -> BrokerOrderSnapshot | None:
        return self._get("broker_order", broker_order_id, BrokerOrderSnapshot)

    def list_broker_orders(self, limit: int = 50) -> list[BrokerOrderSnapshot]:
        return sorted(
            self._list("broker_order", BrokerOrderSnapshot),
            key=lambda snapshot: snapshot.observed_at,
            reverse=True,
        )[:limit]

    def save_position(self, position: PortfolioPosition) -> PortfolioPosition:
        self._put("position", position.symbol.upper(), position)
        return position

    def get_position(self, symbol: str) -> PortfolioPosition | None:
        return self._get("position", symbol.upper(), PortfolioPosition)

    def list_positions(self) -> list[PortfolioPosition]:
        return self._list("position", PortfolioPosition)

    def save_account_state(self, account: AccountState) -> AccountState:
        self._put("account_state", "default", account)
        return account

    def get_account_state(self) -> AccountState | None:
        return self._get("account_state", "default", AccountState)

    def save_price_bars(self, bars: list[PriceBar]) -> list[PriceBar]:
        normalized = []
        for bar in bars:
            saved = bar.model_copy(update={"symbol": bar.symbol.strip().upper()})
            self._put("price_bar", self._bar_id(saved), saved)
            normalized.append(saved)
        return normalized

    def list_price_bars(self, symbol: str, limit: int = 200) -> list[PriceBar]:
        normalized_symbol = symbol.strip().upper()
        bars = [
            bar
            for bar in self._list("price_bar", PriceBar)
            if bar.symbol.upper() == normalized_symbol
        ]
        return sorted(bars, key=lambda bar: bar.timestamp)[-limit:]

    def save_backtest(self, record: BacktestRecord) -> BacktestRecord:
        self._put("backtest", record.id, record)
        return record

    def get_backtest(self, backtest_id: str) -> BacktestRecord | None:
        return self._get("backtest", backtest_id, BacktestRecord)

    def list_backtests(self, symbol: str | None = None, limit: int = 50) -> list[BacktestRecord]:
        records = self._list("backtest", BacktestRecord)
        if symbol is not None:
            normalized_symbol = symbol.strip().upper()
            records = [record for record in records if record.symbol.upper() == normalized_symbol]
        return sorted(records, key=lambda record: record.created_at, reverse=True)[:limit]

    def audit(self, event_type: str, **payload) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (event_type, payload_json, created_at)
                VALUES (?, ?, ?)
                """,
                (event_type, json.dumps(payload, default=str), utc_now().isoformat()),
            )

    def list_audit_events(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_type, payload_json, created_at
                FROM audit_events
                ORDER BY id ASC
                """
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _put(self, kind: str, object_id: str, model: BaseModel) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO objects (kind, id, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(kind, id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    kind,
                    object_id,
                    model.model_dump_json(),
                    utc_now().isoformat(),
                ),
            )

    def _get(self, kind: str, object_id: str, model_type: type[ModelT]) -> ModelT | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM objects WHERE kind = ? AND id = ?",
                (kind, object_id),
            ).fetchone()
        if row is None:
            return None
        return model_type.model_validate_json(row["payload_json"])

    def _list(self, kind: str, model_type: type[ModelT]) -> list[ModelT]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM objects WHERE kind = ?",
                (kind,),
            ).fetchall()
        return [model_type.model_validate_json(row["payload_json"]) for row in rows]

    def _bar_id(self, bar: PriceBar) -> str:
        return f"{bar.symbol.upper()}:{bar.timestamp.isoformat()}"
