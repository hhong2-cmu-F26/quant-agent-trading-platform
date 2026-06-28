from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from .market_data import PriceBar
from .models import AccountState, Agent, AgentMessage, AgentTask, BacktestRecord, BrokerOrderSnapshot, OrderProposal, PortfolioPosition


class Repository(Protocol):
    def add_agent(self, agent: Agent) -> Agent: ...
    def get_agent(self, agent_id: str) -> Agent | None: ...
    def list_agents(self) -> list[Agent]: ...
    def add_task(self, task: AgentTask) -> AgentTask: ...
    def get_task(self, task_id: str) -> AgentTask | None: ...
    def list_tasks(self, status: str | None = None, limit: int = 20) -> list[AgentTask]: ...
    def list_tasks_for_agent(self, agent_id: str, status: str | None = None, limit: int = 20) -> list[AgentTask]: ...
    def save_task(self, task: AgentTask) -> AgentTask: ...
    def add_message(self, message: AgentMessage) -> AgentMessage: ...
    def get_message(self, message_id: str) -> AgentMessage | None: ...
    def list_messages(self, unread_only: bool = False, limit: int = 20) -> list[AgentMessage]: ...
    def list_messages_for_agent(self, agent_id: str, unread_only: bool = False, limit: int = 20) -> list[AgentMessage]: ...
    def save_message(self, message: AgentMessage) -> AgentMessage: ...
    def add_proposal(self, proposal: OrderProposal) -> OrderProposal: ...
    def get_proposal(self, proposal_id: str) -> OrderProposal | None: ...
    def list_proposals(self, status: str | None = None, limit: int = 50) -> list[OrderProposal]: ...
    def save_proposal(self, proposal: OrderProposal) -> OrderProposal: ...
    def save_broker_order(self, snapshot: BrokerOrderSnapshot) -> BrokerOrderSnapshot: ...
    def get_broker_order(self, broker_order_id: str) -> BrokerOrderSnapshot | None: ...
    def list_broker_orders(self, limit: int = 50) -> list[BrokerOrderSnapshot]: ...
    def save_position(self, position: PortfolioPosition) -> PortfolioPosition: ...
    def get_position(self, symbol: str) -> PortfolioPosition | None: ...
    def list_positions(self) -> list[PortfolioPosition]: ...
    def save_account_state(self, account: AccountState) -> AccountState: ...
    def get_account_state(self) -> AccountState | None: ...
    def save_price_bars(self, bars: list[PriceBar]) -> list[PriceBar]: ...
    def list_price_bars(self, symbol: str, limit: int = 200) -> list[PriceBar]: ...
    def save_backtest(self, record: BacktestRecord) -> BacktestRecord: ...
    def get_backtest(self, backtest_id: str) -> BacktestRecord | None: ...
    def list_backtests(self, symbol: str | None = None, limit: int = 50) -> list[BacktestRecord]: ...
    def audit(self, event_type: str, **payload) -> None: ...
    def list_audit_events(self) -> list[dict]: ...


@dataclass
class InMemoryStore:
    agents: dict[str, Agent] = field(default_factory=dict)
    tasks: dict[str, AgentTask] = field(default_factory=dict)
    messages: dict[str, AgentMessage] = field(default_factory=dict)
    proposals: dict[str, OrderProposal] = field(default_factory=dict)
    broker_orders: dict[str, BrokerOrderSnapshot] = field(default_factory=dict)
    positions: dict[str, PortfolioPosition] = field(default_factory=dict)
    account_state: AccountState | None = None
    price_bars: dict[tuple[str, str], PriceBar] = field(default_factory=dict)
    backtests: dict[str, BacktestRecord] = field(default_factory=dict)
    audit_events: list[dict] = field(default_factory=list)

    def add_agent(self, agent: Agent) -> Agent:
        self.agents[agent.id] = agent
        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        return self.agents.get(agent_id)

    def list_agents(self) -> list[Agent]:
        return list(self.agents.values())

    def add_task(self, task: AgentTask) -> AgentTask:
        self.tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> AgentTask | None:
        return self.tasks.get(task_id)

    def list_tasks(self, status: str | None = None, limit: int = 20) -> list[AgentTask]:
        tasks = list(self.tasks.values())
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        return sorted(tasks, key=lambda task: task.created_at)[:limit]

    def list_tasks_for_agent(self, agent_id: str, status: str | None = None, limit: int = 20) -> list[AgentTask]:
        tasks = [task for task in self.tasks.values() if task.agent_id == agent_id]
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        return sorted(tasks, key=lambda task: task.created_at)[:limit]

    def save_task(self, task: AgentTask) -> AgentTask:
        self.tasks[task.id] = task
        return task

    def add_message(self, message: AgentMessage) -> AgentMessage:
        self.messages[message.id] = message
        return message

    def get_message(self, message_id: str) -> AgentMessage | None:
        return self.messages.get(message_id)

    def list_messages(self, unread_only: bool = False, limit: int = 20) -> list[AgentMessage]:
        messages = list(self.messages.values())
        if unread_only:
            messages = [message for message in messages if not message.read]
        return sorted(messages, key=lambda message: message.created_at)[:limit]

    def list_messages_for_agent(self, agent_id: str, unread_only: bool = False, limit: int = 20) -> list[AgentMessage]:
        messages = [message for message in self.messages.values() if message.agent_id == agent_id]
        if unread_only:
            messages = [message for message in messages if not message.read]
        return sorted(messages, key=lambda message: message.created_at)[:limit]

    def save_message(self, message: AgentMessage) -> AgentMessage:
        self.messages[message.id] = message
        return message

    def add_proposal(self, proposal: OrderProposal) -> OrderProposal:
        self.proposals[proposal.id] = proposal
        return proposal

    def get_proposal(self, proposal_id: str) -> OrderProposal | None:
        return self.proposals.get(proposal_id)

    def list_proposals(self, status: str | None = None, limit: int = 50) -> list[OrderProposal]:
        proposals = list(self.proposals.values())
        if status is not None:
            proposals = [proposal for proposal in proposals if proposal.status == status]
        return sorted(proposals, key=lambda proposal: proposal.created_at, reverse=True)[:limit]

    def save_proposal(self, proposal: OrderProposal) -> OrderProposal:
        self.proposals[proposal.id] = proposal
        return proposal

    def save_broker_order(self, snapshot: BrokerOrderSnapshot) -> BrokerOrderSnapshot:
        self.broker_orders[snapshot.broker_order_id] = snapshot
        return snapshot

    def get_broker_order(self, broker_order_id: str) -> BrokerOrderSnapshot | None:
        return self.broker_orders.get(broker_order_id)

    def list_broker_orders(self, limit: int = 50) -> list[BrokerOrderSnapshot]:
        return sorted(self.broker_orders.values(), key=lambda snapshot: snapshot.observed_at, reverse=True)[:limit]

    def save_position(self, position: PortfolioPosition) -> PortfolioPosition:
        self.positions[position.symbol.upper()] = position
        return position

    def get_position(self, symbol: str) -> PortfolioPosition | None:
        return self.positions.get(symbol.upper())

    def list_positions(self) -> list[PortfolioPosition]:
        return list(self.positions.values())

    def save_account_state(self, account: AccountState) -> AccountState:
        self.account_state = account
        return account

    def get_account_state(self) -> AccountState | None:
        return self.account_state

    def save_price_bars(self, bars: list[PriceBar]) -> list[PriceBar]:
        normalized = []
        for bar in bars:
            saved = bar.model_copy(update={"symbol": bar.symbol.strip().upper()})
            self.price_bars[(saved.symbol, saved.timestamp.isoformat())] = saved
            normalized.append(saved)
        return normalized

    def list_price_bars(self, symbol: str, limit: int = 200) -> list[PriceBar]:
        normalized_symbol = symbol.strip().upper()
        bars = [bar for (bar_symbol, _), bar in self.price_bars.items() if bar_symbol == normalized_symbol]
        return sorted(bars, key=lambda bar: bar.timestamp)[-limit:]

    def save_backtest(self, record: BacktestRecord) -> BacktestRecord:
        self.backtests[record.id] = record
        return record

    def get_backtest(self, backtest_id: str) -> BacktestRecord | None:
        return self.backtests.get(backtest_id)

    def list_backtests(self, symbol: str | None = None, limit: int = 50) -> list[BacktestRecord]:
        records = list(self.backtests.values())
        if symbol is not None:
            normalized_symbol = symbol.strip().upper()
            records = [record for record in records if record.symbol.upper() == normalized_symbol]
        return sorted(records, key=lambda record: record.created_at, reverse=True)[:limit]

    def audit(self, event_type: str, **payload) -> None:
        self.audit_events.append(
            {
                "event_type": event_type,
                "payload": payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def list_audit_events(self) -> list[dict]:
        return list(self.audit_events)


store = InMemoryStore()
