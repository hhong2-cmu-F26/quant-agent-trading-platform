from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .broker import MockRobinhoodGateway
from .execution_policy import ExecutionPolicy, ExecutionPolicyConfig
from .orders import OrderWorkflow
from .risk import PortfolioRiskEngine
from .sqlite_store import SQLiteStore
from .store import Repository
from .worker import AgentTaskWorker, TaskRunSummary, build_default_worker


@dataclass(frozen=True)
class WorkerServiceConfig:
    poll_interval_seconds: float = 2.0
    batch_size: int = 10
    max_iterations: int | None = None
    idle_sleep: bool = True


@dataclass
class WorkerServiceStats:
    iterations: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    batches: list[TaskRunSummary] = field(default_factory=list)


class WorkerService:
    """Polls durable agent tasks with a reusable worker instance."""

    def __init__(self, worker: AgentTaskWorker, config: WorkerServiceConfig | None = None):
        self.worker = worker
        self.config = config or WorkerServiceConfig()
        self.stop_requested = False

    def stop(self) -> None:
        self.stop_requested = True

    def run(self) -> WorkerServiceStats:
        stats = WorkerServiceStats()
        while not self.stop_requested:
            summary = self.worker.run_once(limit=self.config.batch_size)
            stats.iterations += 1
            stats.processed += summary.processed
            stats.succeeded += summary.succeeded
            stats.failed += summary.failed
            stats.batches.append(summary)

            if self.config.max_iterations is not None and stats.iterations >= self.config.max_iterations:
                break
            if summary.processed == 0 and self.config.idle_sleep and self.config.poll_interval_seconds > 0:
                time.sleep(self.config.poll_interval_seconds)
        return stats


def build_worker_from_repository(repository: Repository) -> AgentTaskWorker:
    workflow = OrderWorkflow(
        repository,
        PortfolioRiskEngine(repository),
        MockRobinhoodGateway(),
        ExecutionPolicy(ExecutionPolicyConfig(allow_auto_submit=True)),
    )
    return build_default_worker(repository, workflow)


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "trading_platform.db"


def build_service_from_env(config: WorkerServiceConfig) -> WorkerService:
    db_path = os.getenv("TRADING_PLATFORM_DB_PATH", str(default_db_path()))
    repository = SQLiteStore(db_path)
    return WorkerService(build_worker_from_repository(repository), config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the quant agent task worker.")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--max-iterations", type=int, default=None)
    args = parser.parse_args(argv)

    service = build_service_from_env(
        WorkerServiceConfig(
            batch_size=args.batch_size,
            poll_interval_seconds=args.poll_interval,
            max_iterations=args.max_iterations,
        )
    )
    stats = service.run()
    print(
        "worker stopped "
        f"iterations={stats.iterations} processed={stats.processed} "
        f"succeeded={stats.succeeded} failed={stats.failed}"
    )
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
