from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .market_data import FeatureEngine, PriceBar
from .models import AgentTask, utc_now
from .orders import OrderWorkflow
from .store import Repository
from .strategy import MomentumStrategy, MomentumStrategyConfig

TaskHandler = Callable[[AgentTask], dict[str, Any]]


@dataclass
class TaskRunSummary:
    processed: int
    succeeded: int
    failed: int


class AgentTaskWorker:
    """Synchronous task worker for agent OS jobs.

    This is intentionally small and deterministic. A real deployment can run
    this loop from a separate process while keeping the same handler contract.
    """

    def __init__(self, store: Repository):
        self.store = store
        self.handlers: dict[str, TaskHandler] = {}

    def register(self, kind: str, handler: TaskHandler) -> None:
        self.handlers[kind] = handler

    def run_once(self, limit: int = 10) -> TaskRunSummary:
        pending = self.store.list_tasks(status="pending", limit=limit)
        succeeded = 0
        failed = 0

        for task in pending:
            handler = self.handlers.get(task.kind)
            task.status = "running"
            task.started_at = utc_now()
            self.store.save_task(task)

            try:
                if handler is None:
                    raise ValueError(f"no handler registered for task kind: {task.kind}")
                task.result = handler(task)
                task.status = "completed"
                task.completed_at = utc_now()
                task.error = None
                succeeded += 1
                self.store.audit("agent_task_completed", task_id=task.id, kind=task.kind)
            except Exception as exc:
                task.status = "failed"
                task.completed_at = utc_now()
                task.error = str(exc)
                failed += 1
                self.store.audit("agent_task_failed", task_id=task.id, kind=task.kind, error=task.error)
            finally:
                self.store.save_task(task)

        return TaskRunSummary(processed=len(pending), succeeded=succeeded, failed=failed)


class QuantTaskHandlers:
    def __init__(self, workflow: OrderWorkflow):
        self.workflow = workflow
        self.feature_engine = FeatureEngine()

    def momentum_proposal(self, task: AgentTask) -> dict[str, Any]:
        bars_payload = task.payload.get("bars")
        if not isinstance(bars_payload, list):
            raise ValueError("payload.bars must be a list")

        bars = [PriceBar.model_validate(item) for item in bars_payload]
        lookback = int(task.payload.get("lookback", 20))
        features = self.feature_engine.build_snapshot(bars, lookback=lookback)
        strategy = MomentumStrategy(
            MomentumStrategyConfig(
                min_momentum=float(task.payload.get("min_momentum", 0.03)),
                max_volatility=float(task.payload.get("max_volatility", 0.60)),
                target_notional=float(task.payload.get("target_notional", 500.0)),
            )
        )
        proposal_request = strategy.propose(task.agent_id, features)
        if proposal_request is None:
            return {
                "proposal_created": False,
                "reason": "strategy conditions not met",
                "features": features.model_dump(mode="json"),
            }

        proposal = self.workflow.create_proposal(proposal_request)
        return {
            "proposal_created": True,
            "proposal_id": proposal.id,
            "features": features.model_dump(mode="json"),
        }


def build_default_worker(store: Repository, workflow: OrderWorkflow) -> AgentTaskWorker:
    worker = AgentTaskWorker(store)
    quant_handlers = QuantTaskHandlers(workflow)
    worker.register("quant.momentum_proposal", quant_handlers.momentum_proposal)
    return worker

