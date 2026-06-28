from __future__ import annotations

from dataclasses import dataclass

from .models import OrderProposal, OrderSide, RiskDecision
from .store import Repository


@dataclass(frozen=True)
class RiskLimits:
    max_order_notional: float = 1_000.0
    max_quantity: float = 1_000.0
    min_limit_price: float = 0.01
    require_limit_orders: bool = True
    max_symbol_position_notional: float = 5_000.0
    max_symbol_equity_pct: float = 25.0


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()

    def review(self, proposal: OrderProposal) -> RiskDecision:
        reasons: list[str] = []
        checks: dict[str, object] = {}

        symbol = proposal.symbol.strip().upper()
        checks["symbol_normalized"] = symbol
        if not symbol:
            reasons.append("symbol is required")

        checks["quantity"] = proposal.quantity
        if proposal.quantity <= 0:
            reasons.append("quantity must be positive")
        if proposal.quantity > self.limits.max_quantity:
            reasons.append("quantity exceeds max quantity")

        if self.limits.require_limit_orders and proposal.limit_price is None:
            reasons.append("limit price is required")

        if proposal.limit_price is not None:
            checks["limit_price"] = proposal.limit_price
            if proposal.limit_price < self.limits.min_limit_price:
                reasons.append("limit price is too small")
            notional = proposal.limit_price * proposal.quantity
            checks["estimated_notional"] = notional
            if proposal.side == OrderSide.BUY and notional > self.limits.max_order_notional:
                reasons.append("buy notional exceeds max order notional")

        return RiskDecision(approved=not reasons, reasons=reasons, checks=checks)


class PortfolioRiskEngine(RiskEngine):
    """Risk engine that includes account and current-position context."""

    def __init__(self, store: Repository, limits: RiskLimits | None = None):
        super().__init__(limits=limits)
        self.store = store

    def review(self, proposal: OrderProposal) -> RiskDecision:
        decision = super().review(proposal)
        reasons = list(decision.reasons)
        checks = dict(decision.checks)

        account = self.store.get_account_state()
        if account:
            checks["buying_power"] = account.buying_power
            checks["account_equity"] = account.equity
        else:
            checks["buying_power"] = None
            checks["account_equity"] = None

        estimated_notional = checks.get("estimated_notional")
        if proposal.side == OrderSide.BUY and estimated_notional is not None:
            notional = float(estimated_notional)
            if account and account.buying_power < notional:
                reasons.append("buy notional exceeds buying power")

            current = self.store.get_position(proposal.symbol)
            current_notional = 0.0
            if current:
                current_notional = abs(current.quantity) * current.average_price
            projected_symbol_notional = current_notional + notional
            checks["current_symbol_notional"] = current_notional
            checks["projected_symbol_notional"] = projected_symbol_notional
            if projected_symbol_notional > self.limits.max_symbol_position_notional:
                reasons.append("projected symbol notional exceeds concentration limit")
            if account and account.equity > 0:
                projected_pct = projected_symbol_notional / account.equity * 100
                checks["projected_symbol_equity_pct"] = projected_pct
                if projected_pct > self.limits.max_symbol_equity_pct:
                    reasons.append("projected symbol exposure exceeds equity percentage limit")

        return RiskDecision(approved=not reasons, reasons=reasons, checks=checks)
