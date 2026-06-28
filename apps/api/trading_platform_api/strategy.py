from __future__ import annotations

from dataclasses import dataclass

from .market_data import FeatureSnapshot
from .models import OrderProposalCreate, OrderSide, OrderType


@dataclass(frozen=True)
class MomentumStrategyConfig:
    strategy_id: str = "long_momentum_v1"
    min_momentum: float = 0.03
    max_volatility: float = 0.60
    target_notional: float = 500.0
    limit_price_buffer_pct: float = 0.002


class MomentumStrategy:
    """Long-only Robinhood-compatible starter strategy."""

    def __init__(self, config: MomentumStrategyConfig | None = None):
        self.config = config or MomentumStrategyConfig()

    def propose(self, agent_id: str, features: FeatureSnapshot) -> OrderProposalCreate | None:
        if features.warnings:
            return None
        if features.momentum < self.config.min_momentum:
            return None
        if features.realized_volatility > self.config.max_volatility:
            return None
        if features.close < features.moving_average:
            return None

        limit_price = round(features.close * (1 + self.config.limit_price_buffer_pct), 2)
        quantity = max(1, int(self.config.target_notional // limit_price))
        if quantity <= 0:
            return None

        return OrderProposalCreate(
            agent_id=agent_id,
            symbol=features.symbol,
            side=OrderSide.BUY,
            quantity=float(quantity),
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            strategy_id=self.config.strategy_id,
            rationale=(
                f"{features.symbol} passed momentum screen: "
                f"momentum={features.momentum:.4f}, "
                f"volatility={features.realized_volatility:.4f}, "
                f"close={features.close:.2f}, "
                f"ma={features.moving_average:.2f}"
            ),
        )

