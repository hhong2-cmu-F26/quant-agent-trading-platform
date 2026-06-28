from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


class DataQualityIssue(BaseModel):
    code: str
    severity: str
    message: str
    timestamp: datetime | None = None


class DataQualityReport(BaseModel):
    symbol: str
    checked_at: datetime
    bar_count: int
    issue_count: int
    passed: bool
    issues: list[DataQualityIssue] = Field(default_factory=list)


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


class DataQualityChecker:
    """Deterministic quality checks for stored market bars."""

    def check(
        self,
        bars: list[PriceBar],
        *,
        expected_symbol: str | None = None,
        max_staleness: timedelta | None = None,
        as_of: datetime | None = None,
    ) -> DataQualityReport:
        checked_at = as_of or datetime.now(timezone.utc)
        normalized_expected = expected_symbol.strip().upper() if expected_symbol else None
        issues: list[DataQualityIssue] = []

        if not bars:
            symbol = normalized_expected or ""
            return DataQualityReport(
                symbol=symbol,
                checked_at=checked_at,
                bar_count=0,
                issue_count=1,
                passed=False,
                issues=[
                    DataQualityIssue(
                        code="no_bars",
                        severity="error",
                        message="no bars available",
                    )
                ],
            )

        ordered = sorted(bars, key=lambda bar: bar.timestamp)
        symbol = normalized_expected or ordered[-1].symbol.strip().upper()
        seen_timestamps: set[datetime] = set()
        intervals: list[float] = []

        for index, bar in enumerate(ordered):
            bar_symbol = bar.symbol.strip().upper()
            if normalized_expected and bar_symbol != normalized_expected:
                issues.append(
                    DataQualityIssue(
                        code="symbol_mismatch",
                        severity="error",
                        message=f"expected {normalized_expected}, got {bar_symbol}",
                        timestamp=bar.timestamp,
                    )
                )

            if bar.timestamp in seen_timestamps:
                issues.append(
                    DataQualityIssue(
                        code="duplicate_timestamp",
                        severity="error",
                        message="duplicate bar timestamp",
                        timestamp=bar.timestamp,
                    )
                )
            seen_timestamps.add(bar.timestamp)

            self._check_bar_values(bar, issues)

            if index > 0:
                delta = (bar.timestamp - ordered[index - 1].timestamp).total_seconds()
                if delta > 0:
                    intervals.append(delta)
                else:
                    issues.append(
                        DataQualityIssue(
                            code="non_increasing_timestamp",
                            severity="error",
                            message="bar timestamps must increase",
                            timestamp=bar.timestamp,
                        )
                    )

        if intervals:
            expected_interval = min(intervals)
            for index in range(1, len(ordered)):
                delta = (ordered[index].timestamp - ordered[index - 1].timestamp).total_seconds()
                if delta > expected_interval * 1.5:
                    issues.append(
                        DataQualityIssue(
                            code="missing_interval",
                            severity="warning",
                            message=f"gap of {int(delta)} seconds exceeds expected interval {int(expected_interval)} seconds",
                            timestamp=ordered[index].timestamp,
                        )
                    )

        if max_staleness is not None:
            latest = ordered[-1].timestamp
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            if checked_at - latest > max_staleness:
                issues.append(
                    DataQualityIssue(
                        code="stale_data",
                        severity="warning",
                        message=f"latest bar is older than {max_staleness}",
                        timestamp=latest,
                    )
                )

        return DataQualityReport(
            symbol=symbol,
            checked_at=checked_at,
            bar_count=len(ordered),
            issue_count=len(issues),
            passed=not any(issue.severity == "error" for issue in issues),
            issues=issues,
        )

    def _check_bar_values(self, bar: PriceBar, issues: list[DataQualityIssue]) -> None:
        values = {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for field, value in values.items():
            try:
                parsed = float(value)
            except Exception:
                parsed = float("nan")
            if not isfinite(parsed):
                issues.append(
                    DataQualityIssue(
                        code=f"{field}_not_finite",
                        severity="error",
                        message=f"{field} must be finite",
                        timestamp=bar.timestamp,
                    )
                )

        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            issues.append(
                DataQualityIssue(
                    code="non_positive_price",
                    severity="error",
                    message="OHLC prices must be positive",
                    timestamp=bar.timestamp,
                )
            )
        if bar.volume < 0:
            issues.append(
                DataQualityIssue(
                    code="negative_volume",
                    severity="error",
                    message="volume must be non-negative",
                    timestamp=bar.timestamp,
                )
            )
        if bar.high < bar.low:
            issues.append(
                DataQualityIssue(
                    code="high_below_low",
                    severity="error",
                    message="high price cannot be below low price",
                    timestamp=bar.timestamp,
                )
            )
        if not (bar.low <= bar.open <= bar.high):
            issues.append(
                DataQualityIssue(
                    code="open_outside_range",
                    severity="warning",
                    message="open price is outside low/high range",
                    timestamp=bar.timestamp,
                )
            )
        if not (bar.low <= bar.close <= bar.high):
            issues.append(
                DataQualityIssue(
                    code="close_outside_range",
                    severity="warning",
                    message="close price is outside low/high range",
                    timestamp=bar.timestamp,
                )
            )
