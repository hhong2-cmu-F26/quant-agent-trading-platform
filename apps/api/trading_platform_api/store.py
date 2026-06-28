from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import Agent, AgentMessage, AgentTask, OrderProposal


@dataclass
class InMemoryStore:
    agents: dict[str, Agent] = field(default_factory=dict)
    tasks: dict[str, AgentTask] = field(default_factory=dict)
    messages: dict[str, AgentMessage] = field(default_factory=dict)
    proposals: dict[str, OrderProposal] = field(default_factory=dict)
    audit_events: list[dict] = field(default_factory=list)

    def audit(self, event_type: str, **payload) -> None:
        self.audit_events.append(
            {
                "event_type": event_type,
                "payload": payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )


store = InMemoryStore()
