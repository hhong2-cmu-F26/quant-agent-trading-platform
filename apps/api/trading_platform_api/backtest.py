from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from .market_data import FeatureEngine, FeatureSnapshot, PriceBar
from .models import BacktestRecord, OrderSide
from .paper import PaperMetrics, PaperPortfolio, PaperTrade, PaperTradingConfig, PaperTradingEngine
from .strategy import MomentumStrategy, MomentumStrategyConfig


@dataclass(frozen=True)
class MomentumBacktestConfig:
    lookback: int = 20
    min_momentum: float = 0.03
    max_volatility: float = 0.60
    target_notional: float = 500.0
    starting_cash: float = 100_000.0


class MomentumBacktestResult(BaseModel):
    symbol: str
    lookback: int
    bar_count: int
    feature_count: int
    signal_count: int
    trades: list[PaperTrade] = Field(default_factory=list)
    metrics: PaperMetrics
    portfolio: PaperPortfolio
    final_features: FeatureSnapshot | None = None


class MomentumBacktestEngine:
    """Small deterministic backtest for the starter long-only momentum strategy."""

    def __init__(self, config: MomentumBacktestConfig | None = None):
        self.config = config or MomentumBacktestConfig()
        self.feature_engine = FeatureEngine()
        self.strategy = MomentumStrategy(
            MomentumStrategyConfig(
                min_momentum=self.config.min_momentum,
                max_volatility=self.config.max_volatility,
                target_notional=self.config.target_notional,
            )
        )
        self.paper = PaperTradingEngine(PaperTradingConfig(starting_cash=self.config.starting_cash))

    def run(self, bars: list[PriceBar]) -> MomentumBacktestResult:
        if len(bars) < self.config.lookback:
            raise ValueError("not enough bars for backtest lookback")

        ordered = sorted(bars, key=lambda bar: bar.timestamp)
        symbol = ordered[-1].symbol.strip().upper()
        if any(bar.symbol.strip().upper() != symbol for bar in ordered):
            raise ValueError("all bars must have the same symbol")

        trades: list[PaperTrade] = []
        in_position = False
        feature_count = 0
        signal_count = 0
        final_features = None

        for index in range(self.config.lookback, len(ordered)):
            window = ordered[: index + 1]
            features = self.feature_engine.build_snapshot(window, lookback=self.config.lookback)
            feature_count += 1
            final_features = features
            if in_position:
                continue

            proposal = self.strategy.propose("backtest", features)
            if proposal is None:
                continue

            trades.append(
                PaperTrade(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    quantity=proposal.quantity,
                    price=ordered[index].close,
                )
            )
            in_position = True
            signal_count += 1

        if in_position:
            quantity = sum(trade.quantity for trade in trades if trade.side == OrderSide.BUY)
            if quantity > 0:
                trades.append(
                    PaperTrade(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        quantity=quantity,
                        price=ordered[-1].close,
                    )
                )

        portfolio, metrics = self.paper.replay(trades, marks={symbol: ordered[-1].close})
        return MomentumBacktestResult(
            symbol=symbol,
            lookback=self.config.lookback,
            bar_count=len(ordered),
            feature_count=feature_count,
            signal_count=signal_count,
            trades=trades,
            metrics=metrics,
            portfolio=portfolio,
            final_features=final_features,
        )


def backtest_record_from_result(
    result: MomentumBacktestResult,
    config: MomentumBacktestConfig,
    *,
    strategy_id: str = "long_momentum_v1",
) -> BacktestRecord:
    return BacktestRecord(
        strategy_id=strategy_id,
        symbol=result.symbol,
        config={
            "lookback": config.lookback,
            "min_momentum": config.min_momentum,
            "max_volatility": config.max_volatility,
            "target_notional": config.target_notional,
            "starting_cash": config.starting_cash,
        },
        metrics=result.metrics.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
    )
