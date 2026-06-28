from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from .models import Agent, AgentMessage, AgentTask, OrderProposal


class Repository(Protocol):
    def add_agent(self, agent: Agent) -> Agent: ...
    def get_agent(self, agent_id: str) -> Agent | None: ...
    def list_agents(self) -> list[Agent]: ...
    def add_task(self, task: AgentTask) -> AgentTask: ...
    def get_task(self, task_id: str) -> AgentTask | None: ...
    def list_tasks_for_agent(self, agent_id: str, status: str | None = None, limit: int = 20) -> list[AgentTask]: ...
    def save_task(self, task: AgentTask) -> AgentTask: ...
    def add_message(self, message: AgentMessage) -> AgentMessage: ...
    def get_message(self, message_id: str) -> AgentMessage | None: ...
    def list_messages_for_agent(self, agent_id: str, unread_only: bool = False, limit: int = 20) -> list[AgentMessage]: ...
    def save_message(self, message: AgentMessage) -> AgentMessage: ...
    def add_proposal(self, proposal: OrderProposal) -> OrderProposal: ...
    def get_proposal(self, proposal_id: str) -> OrderProposal | None: ...
    def save_proposal(self, proposal: OrderProposal) -> OrderProposal: ...
    def audit(self, event_type: str, **payload) -> None: ...
    def list_audit_events(self) -> list[dict]: ...


@dataclass
class InMemoryStore:
    agents: dict[str, Agent] = field(default_factory=dict)
    tasks: dict[str, AgentTask] = field(default_factory=dict)
    messages: dict[str, AgentMessage] = field(default_factory=dict)
    proposals: dict[str, OrderProposal] = field(default_factory=dict)
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

    def save_proposal(self, proposal: OrderProposal) -> OrderProposal:
        self.proposals[proposal.id] = proposal
        return proposal

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
