from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import asyncio
from datetime import timedelta

from .backtest import MomentumBacktestConfig, MomentumBacktestEngine, backtest_record_from_result
from .market_data import DataQualityChecker, FeatureEngine, PriceBar
from .models import AgentTask, utc_now
from .orders import OrderWorkflow
from .portfolio_sync import PortfolioSyncService
from .scoring import StrategyScorer, StrategyScoringConfig
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
        lookback = int(task.payload.get("lookback", 20))
        if isinstance(bars_payload, list):
            bars = [PriceBar.model_validate(item) for item in bars_payload]
        else:
            symbol = str(task.payload.get("symbol") or "").strip()
            if not symbol:
                raise ValueError("payload.bars or payload.symbol is required")
            bars = self.workflow.store.list_price_bars(symbol, limit=int(task.payload.get("limit", 200)))

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


class MarketDataTaskHandlers:
    def __init__(self, store: Repository):
        self.store = store
        self.quality_checker = DataQualityChecker()

    def quality_check(self, task: AgentTask) -> dict[str, Any]:
        symbol = str(task.payload.get("symbol") or "").strip()
        if not symbol:
            raise ValueError("payload.symbol is required")
        limit = int(task.payload.get("limit", 200))
        max_staleness_seconds = task.payload.get("max_staleness_seconds")
        max_staleness = timedelta(seconds=int(max_staleness_seconds)) if max_staleness_seconds is not None else None
        bars = self.store.list_price_bars(symbol, limit=limit)
        report = self.quality_checker.check(
            bars,
            expected_symbol=symbol,
            max_staleness=max_staleness,
        )
        return report.model_dump(mode="json")


class BacktestTaskHandlers:
    def __init__(self, store: Repository):
        self.store = store

    def momentum(self, task: AgentTask) -> dict[str, Any]:
        bars_payload = task.payload.get("bars")
        if isinstance(bars_payload, list):
            bars = [PriceBar.model_validate(item) for item in bars_payload]
        else:
            symbol = str(task.payload.get("symbol") or "").strip()
            if not symbol:
                raise ValueError("payload.bars or payload.symbol is required")
            bars = self.store.list_price_bars(symbol, limit=int(task.payload.get("limit", 500)))

        engine = MomentumBacktestEngine(
            MomentumBacktestConfig(
                lookback=int(task.payload.get("lookback", 20)),
                min_momentum=float(task.payload.get("min_momentum", 0.03)),
                max_volatility=float(task.payload.get("max_volatility", 0.60)),
                target_notional=float(task.payload.get("target_notional", 500.0)),
                starting_cash=float(task.payload.get("starting_cash", 100_000.0)),
            )
        )
        result = engine.run(bars)
        record = self.store.save_backtest(backtest_record_from_result(result, engine.config))
        self.store.audit("backtest_recorded", backtest_id=record.id, symbol=record.symbol, strategy_id=record.strategy_id)
        return {
            "backtest_id": record.id,
            "record": record.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }


class StrategyScoringTaskHandlers:
    def __init__(self, store: Repository):
        self.store = store

    def score_backtests(self, task: AgentTask) -> dict[str, Any]:
        symbol = task.payload.get("symbol")
        symbol_filter = str(symbol).strip() if symbol is not None else None
        records = self.store.list_backtests(
            symbol=symbol_filter or None,
            limit=int(task.payload.get("limit", 50)),
        )
        scorer = StrategyScorer(
            StrategyScoringConfig(
                min_trades=int(task.payload.get("min_trades", 1)),
                drawdown_weight=float(task.payload.get("drawdown_weight", 1.0)),
                rejected_trade_penalty=float(task.payload.get("rejected_trade_penalty", 2.0)),
                low_trade_penalty=float(task.payload.get("low_trade_penalty", 5.0)),
            )
        )
        scores = scorer.score(records)
        return {
            "score_count": len(scores),
            "scores": [score.model_dump(mode="json") for score in scores],
        }


class PortfolioTaskHandlers:
    def __init__(self, workflow: OrderWorkflow):
        self.sync_service = PortfolioSyncService(workflow.store, workflow.broker)

    def sync(self, task: AgentTask) -> dict[str, Any]:
        result = asyncio.run(self.sync_service.sync())
        return {
            "account": result["account"].model_dump(mode="json"),
            "positions": [position.model_dump(mode="json") for position in result["positions"]],
            "position_count": result["position_count"],
        }


def build_default_worker(store: Repository, workflow: OrderWorkflow) -> AgentTaskWorker:
    worker = AgentTaskWorker(store)
    quant_handlers = QuantTaskHandlers(workflow)
    market_data_handlers = MarketDataTaskHandlers(store)
    backtest_handlers = BacktestTaskHandlers(store)
    scoring_handlers = StrategyScoringTaskHandlers(store)
    portfolio_handlers = PortfolioTaskHandlers(workflow)
    worker.register("quant.momentum_proposal", quant_handlers.momentum_proposal)
    worker.register("market_data.quality_check", market_data_handlers.quality_check)
    worker.register("backtest.momentum", backtest_handlers.momentum)
    worker.register("strategy.score_backtests", scoring_handlers.score_backtests)
    worker.register("portfolio.sync", portfolio_handlers.sync)
    return worker
