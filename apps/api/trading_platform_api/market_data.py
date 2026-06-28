from __future__ import annotations

from datetime import datetime
from math import isfinite, sqrt
from statistics import mean, pstdev

from pydantic import BaseModel, Field


class PriceBar(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class FeatureSnapshot(BaseModel):
    symbol: str
    timestamp: datetime
    close: float
    lookback: int
    momentum: float
    moving_average: float
    realized_volatility: float
    volume_average: float
    observations: int
    warnings: list[str] = Field(default_factory=list)


class FeatureEngine:
    """Deterministic market feature generation for strategy code."""

    def build_snapshot(self, bars: list[PriceBar], lookback: int = 20) -> FeatureSnapshot:
        if lookback < 2:
            raise ValueError("lookback must be at least 2")
        if len(bars) < 2:
            raise ValueError("at least two bars are required")

        ordered = sorted(bars, key=lambda bar: bar.timestamp)
        symbol = ordered[-1].symbol.upper()
        if any(bar.symbol.upper() != symbol for bar in ordered):
            raise ValueError("all bars must have the same symbol")

        window = ordered[-lookback:]
        closes = [self._positive(bar.close, "close") for bar in window]
        volumes = [max(0.0, self._finite(bar.volume, "volume")) for bar in window]
        returns = [
            (closes[index] / closes[index - 1]) - 1.0
            for index in range(1, len(closes))
            if closes[index - 1] > 0
        ]

        warnings: list[str] = []
        if len(ordered) < lookback:
            warnings.append("insufficient lookback history")
        if any(bar.volume <= 0 for bar in window):
            warnings.append("non-positive volume present")

        first_close = closes[0]
        last_close = closes[-1]
        volatility = pstdev(returns) * sqrt(252) if len(returns) > 1 else 0.0
        return FeatureSnapshot(
            symbol=symbol,
            timestamp=ordered[-1].timestamp,
            close=last_close,
            lookback=lookback,
            momentum=(last_close / first_close) - 1.0,
            moving_average=mean(closes),
            realized_volatility=volatility,
            volume_average=mean(volumes),
            observations=len(window),
            warnings=warnings,
        )

    def _positive(self, value: float, field: str) -> float:
        parsed = self._finite(value, field)
        if parsed <= 0:
            raise ValueError(f"{field} must be positive")
        return parsed

    def _finite(self, value: float, field: str) -> float:
        parsed = float(value)
        if not isfinite(parsed):
            raise ValueError(f"{field} must be finite")
        return parsed

