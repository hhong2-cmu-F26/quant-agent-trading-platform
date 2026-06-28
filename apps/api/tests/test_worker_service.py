import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.agent_os import AgentOS
from trading_platform_api.models import Agent, AgentRole, AgentTask
from trading_platform_api.store import InMemoryStore
from trading_platform_api.worker import AgentTaskWorker
from trading_platform_api.worker_service import WorkerService, WorkerServiceConfig, main


def test_worker_service_polls_until_max_iterations():
    store = InMemoryStore()
    agent_os = AgentOS(store)
    agent = agent_os.register_agent(Agent(name="service-agent", role=AgentRole.MONITORING))
    agent_os.create_task(AgentTask(agent_id=agent.id, kind="ops.ping"))
    worker = AgentTaskWorker(store)
    worker.register("ops.ping", lambda task: {"ok": True})
    service = WorkerService(
        worker,
        WorkerServiceConfig(
            batch_size=1,
            max_iterations=2,
            poll_interval_seconds=0,
            idle_sleep=False,
        ),
    )

    stats = service.run()

    assert stats.iterations == 2
    assert stats.processed == 1
    assert stats.succeeded == 1
    assert store.list_tasks(status="completed")[0].result == {"ok": True}


def test_worker_service_cli_runs_single_iteration(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_PLATFORM_DB_PATH", str(tmp_path / "worker.db"))

    exit_code = main(["--max-iterations", "1", "--poll-interval", "0"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "iterations=1" in captured.out
    assert "processed=0" in captured.out
