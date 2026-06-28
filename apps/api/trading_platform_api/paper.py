from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from pydantic import BaseModel, Field

from .models import OrderSide


class PaperTrade(BaseModel):
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fee: float = 0.0


class PaperPosition(BaseModel):
    symbol: str
    quantity: float
    average_price: float


class PaperPortfolio(BaseModel):
    starting_cash: float
    cash: float
    positions: dict[str, PaperPosition] = Field(default_factory=dict)
    equity_curve: list[float] = Field(default_factory=list)
    trade_count: int = 0
    rejected_trades: list[str] = Field(default_factory=list)


class PaperMetrics(BaseModel):
    starting_cash: float
    ending_equity: float
    return_pct: float
    max_drawdown_pct: float
    trade_count: int
    rejected_trade_count: int
    risk_adjusted_score: float


@dataclass(frozen=True)
class PaperTradingConfig:
    starting_cash: float = 100_000.0
    max_position_pct: float = 25.0
    drawdown_penalty: float = 1.0


class PaperTradingEngine:
    """Long-only paper trading replay used before Robinhood live execution."""

    def __init__(self, config: PaperTradingConfig | None = None):
        self.config = config or PaperTradingConfig()

    def replay(self, trades: list[PaperTrade], marks: dict[str, float] | None = None) -> tuple[PaperPortfolio, PaperMetrics]:
        portfolio = PaperPortfolio(
            starting_cash=self.config.starting_cash,
            cash=self.config.starting_cash,
            equity_curve=[self.config.starting_cash],
        )
        mark_prices = {symbol.upper(): price for symbol, price in (marks or {}).items()}

        for trade in trades:
            try:
                self._apply_trade(portfolio, trade)
            except ValueError as exc:
                portfolio.rejected_trades.append(str(exc))
                continue

            equity = self._equity(portfolio, mark_prices)
            portfolio.equity_curve.append(equity)
            if self._max_position_pct(portfolio, mark_prices, equity) > self.config.max_position_pct:
                portfolio.rejected_trades.append(f"max_position_pct_exceeded:{trade.symbol.upper()}")

        ending_equity = self._equity(portfolio, mark_prices)
        if portfolio.equity_curve[-1] != ending_equity:
            portfolio.equity_curve.append(ending_equity)
        max_drawdown = self._max_drawdown(portfolio.equity_curve)
        return_pct = ((ending_equity - portfolio.starting_cash) / portfolio.starting_cash) * 100
        metrics = PaperMetrics(
            starting_cash=portfolio.starting_cash,
            ending_equity=ending_equity,
            return_pct=return_pct,
            max_drawdown_pct=max_drawdown,
            trade_count=portfolio.trade_count,
            rejected_trade_count=len(portfolio.rejected_trades),
            risk_adjusted_score=return_pct - max_drawdown * self.config.drawdown_penalty,
        )
        return portfolio, metrics

    def _apply_trade(self, portfolio: PaperPortfolio, trade: PaperTrade) -> None:
        symbol = trade.symbol.strip().upper()
        quantity = self._positive(trade.quantity, "quantity")
        price = self._positive(trade.price, "price")
        fee = max(0.0, self._finite(trade.fee, "fee"))
        position = portfolio.positions.get(symbol)

        if trade.side == OrderSide.BUY:
            cost = quantity * price + fee
            if portfolio.cash < cost:
                raise ValueError(f"insufficient_cash:{symbol}")
            if position:
                new_quantity = position.quantity + quantity
                position.average_price = ((position.quantity * position.average_price) + (quantity * price)) / new_quantity
                position.quantity = new_quantity
            else:
                portfolio.positions[symbol] = PaperPosition(symbol=symbol, quantity=quantity, average_price=price)
            portfolio.cash -= cost
        elif trade.side == OrderSide.SELL:
            if not position or position.quantity < quantity:
                raise ValueError(f"insufficient_position:{symbol}")
            proceeds = quantity * price - fee
            position.quantity -= quantity
            if position.quantity <= 1e-12:
                portfolio.positions.pop(symbol, None)
            portfolio.cash += proceeds
        else:
            raise ValueError(f"unsupported_side:{trade.side}")

        portfolio.trade_count += 1

    def _equity(self, portfolio: PaperPortfolio, marks: dict[str, float]) -> float:
        equity = portfolio.cash
        for symbol, position in portfolio.positions.items():
            mark = marks.get(symbol, position.average_price)
            equity += position.quantity * mark
        return equity

    def _max_position_pct(self, portfolio: PaperPortfolio, marks: dict[str, float], equity: float) -> float:
        if equity <= 0 or not portfolio.positions:
            return 0.0
        max_notional = max(
            position.quantity * marks.get(symbol, position.average_price)
            for symbol, position in portfolio.positions.items()
        )
        return (max_notional / equity) * 100

    def _max_drawdown(self, equity_curve: list[float]) -> float:
        peak = equity_curve[0] if equity_curve else 0.0
        max_drawdown = 0.0
        for equity in equity_curve:
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak * 100)
        return max_drawdown

    def _positive(self, value: float, field: str) -> float:
        parsed = self._finite(value, field)
        if parsed <= 0:
            raise ValueError(f"{field}_must_be_positive")
        return parsed

    def _finite(self, value: float, field: str) -> float:
        parsed = float(value)
        if not isfinite(parsed):
            raise ValueError(f"{field}_must_be_finite")
        return parsed

