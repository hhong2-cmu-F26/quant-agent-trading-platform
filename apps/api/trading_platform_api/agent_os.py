from __future__ import annotations

from .models import Agent, AgentMessage, AgentTask, utc_now
from .store import Repository


class AgentOS:
    def __init__(self, store: Repository):
        self.store = store

    def register_agent(self, agent: Agent) -> Agent:
        if any(existing.name == agent.name for existing in self.store.list_agents()):
            raise ValueError("agent name already exists")
        self.store.add_agent(agent)
        self.store.audit("agent_registered", agent_id=agent.id, role=agent.role)
        return agent

    def create_task(self, task: AgentTask) -> AgentTask:
        if not self.store.get_agent(task.agent_id):
            raise ValueError("agent not found")
        self.store.add_task(task)
        self.store.audit("agent_task_created", task_id=task.id, agent_id=task.agent_id, kind=task.kind)
        return task

    def send_message(self, message: AgentMessage) -> AgentMessage:
        if not self.store.get_agent(message.agent_id):
            raise ValueError("agent not found")
        self.store.add_message(message)
        self.store.audit("agent_message_sent", message_id=message.id, agent_id=message.agent_id, kind=message.kind)
        return message

    def heartbeat(self, agent_id: str, limit: int = 20) -> dict:
        if not self.store.get_agent(agent_id):
            raise ValueError("agent not found")

        pending_tasks = self.store.list_tasks_for_agent(agent_id, status="pending", limit=limit)
        unread_messages = self.store.list_messages_for_agent(agent_id, unread_only=True, limit=limit)

        now = utc_now()
        for task in pending_tasks:
            task.read_at = now
            self.store.save_task(task)
        for message in unread_messages:
            message.read = True
            self.store.save_message(message)

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
