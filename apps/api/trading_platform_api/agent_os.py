from __future__ import annotations

from .models import Agent, AgentMessage, AgentTask, utc_now
from .store import InMemoryStore


class AgentOS:
    def __init__(self, store: InMemoryStore):
        self.store = store

    def register_agent(self, agent: Agent) -> Agent:
        if any(existing.name == agent.name for existing in self.store.agents.values()):
            raise ValueError("agent name already exists")
        self.store.agents[agent.id] = agent
        self.store.audit("agent_registered", agent_id=agent.id, role=agent.role)
        return agent

    def create_task(self, task: AgentTask) -> AgentTask:
        if task.agent_id not in self.store.agents:
            raise ValueError("agent not found")
        self.store.tasks[task.id] = task
        self.store.audit("agent_task_created", task_id=task.id, agent_id=task.agent_id, kind=task.kind)
        return task

    def send_message(self, message: AgentMessage) -> AgentMessage:
        if message.agent_id not in self.store.agents:
            raise ValueError("agent not found")
        self.store.messages[message.id] = message
        self.store.audit("agent_message_sent", message_id=message.id, agent_id=message.agent_id, kind=message.kind)
        return message

    def heartbeat(self, agent_id: str, limit: int = 20) -> dict:
        if agent_id not in self.store.agents:
            raise ValueError("agent not found")

        pending_tasks = [
            task for task in self.store.tasks.values()
            if task.agent_id == agent_id and task.status == "pending"
        ][:limit]
        unread_messages = [
            message for message in self.store.messages.values()
            if message.agent_id == agent_id and not message.read
        ][:limit]

        now = utc_now()
        for task in pending_tasks:
            task.read_at = now
        for message in unread_messages:
            message.read = True

        self.store.audit(
            "agent_heartbeat",
            agent_id=agent_id,
            task_count=len(pending_tasks),
            message_count=len(unread_messages),
        )
        return {
            "agent_id": agent_id,
            "recommended_poll_interval_seconds": 30,
            "tasks": pending_tasks,
            "messages": unread_messages,
        }

