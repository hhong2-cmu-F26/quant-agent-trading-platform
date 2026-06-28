from __future__ import annotations

from dataclasses import dataclass

from .models import OrderProposal, OrderSide, RiskDecision


@dataclass(frozen=True)
class RiskLimits:
    max_order_notional: float = 1_000.0
    max_quantity: float = 1_000.0
    min_limit_price: float = 0.01
    require_limit_orders: bool = True


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

