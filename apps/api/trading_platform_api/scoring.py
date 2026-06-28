from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from .models import BacktestRecord


class StrategyScoreCard(BaseModel):
    backtest_id: str
    strategy_id: str
    symbol: str
    score: float
    rank: int = 0
    return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    trade_count: int = 0
    rejected_trade_count: int = 0
    reasons: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class StrategyScoringConfig:
    min_trades: int = 1
    drawdown_weight: float = 1.0
    rejected_trade_penalty: float = 2.0
    low_trade_penalty: float = 5.0


class StrategyScorer:
    """Ranks backtest records using deterministic risk-adjusted metrics."""

    def __init__(self, config: StrategyScoringConfig | None = None):
        self.config = config or StrategyScoringConfig()

    def score(self, records: list[BacktestRecord]) -> list[StrategyScoreCard]:
        cards = [self._score_record(record) for record in records]
        cards.sort(key=lambda card: (card.score, card.return_pct, -card.max_drawdown_pct), reverse=True)
        return [card.model_copy(update={"rank": index + 1}) for index, card in enumerate(cards)]

    def _score_record(self, record: BacktestRecord) -> StrategyScoreCard:
        metrics = record.metrics or {}
        return_pct = self._number(metrics.get("return_pct"))
        max_drawdown_pct = max(0.0, self._number(metrics.get("max_drawdown_pct")))
        trade_count = int(self._number(metrics.get("trade_count")))
        rejected_trade_count = int(self._number(metrics.get("rejected_trade_count")))
        reasons: list[str] = []

        score = return_pct - (max_drawdown_pct * self.config.drawdown_weight)
        if rejected_trade_count:
            penalty = rejected_trade_count * self.config.rejected_trade_penalty
            score -= penalty
            reasons.append(f"rejected_trade_penalty:{penalty:.2f}")
        if trade_count < self.config.min_trades:
            score -= self.config.low_trade_penalty
            reasons.append("insufficient_trade_count")
        if max_drawdown_pct:
            reasons.append(f"drawdown_penalty:{max_drawdown_pct * self.config.drawdown_weight:.2f}")

        return StrategyScoreCard(
            backtest_id=record.id,
            strategy_id=record.strategy_id,
            symbol=record.symbol,
            score=round(score, 6),
            return_pct=return_pct,
            max_drawdown_pct=max_drawdown_pct,
            trade_count=trade_count,
            rejected_trade_count=rejected_trade_count,
            reasons=reasons,
        )

    def _number(self, value: object) -> float:
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
