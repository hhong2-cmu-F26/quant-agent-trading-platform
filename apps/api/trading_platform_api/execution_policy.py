from __future__ import annotations

from dataclasses import dataclass

from .models import ExecutionPolicyDecision, OrderProposal


@dataclass(frozen=True)
class ExecutionPolicyConfig:
    allow_auto_submit: bool = False
    block_broker_warnings: bool = True
    max_reviewed_notional: float = 1_000.0


class ExecutionPolicy:
    """Final deterministic gate between broker review and live submission."""

    def __init__(self, config: ExecutionPolicyConfig | None = None):
        self.config = config or ExecutionPolicyConfig()

    def evaluate(self, proposal: OrderProposal) -> ExecutionPolicyDecision:
        reasons: list[str] = []
        checks: dict[str, object] = {
            "allow_auto_submit": self.config.allow_auto_submit,
            "block_broker_warnings": self.config.block_broker_warnings,
            "max_reviewed_notional": self.config.max_reviewed_notional,
        }

        if not proposal.risk or not proposal.risk.approved:
            reasons.append("risk review is not approved")

        if not proposal.broker_review:
            reasons.append("broker review is required")
        elif not proposal.broker_review.approved:
            reasons.append("broker review is not approved")
        else:
            reviewed_notional = proposal.broker_review.estimated_notional
            checks["reviewed_notional"] = reviewed_notional
            if reviewed_notional is not None and reviewed_notional > self.config.max_reviewed_notional:
                reasons.append("reviewed notional exceeds execution policy limit")
            if self.config.block_broker_warnings and proposal.broker_review.warnings:
                checks["broker_warnings"] = proposal.broker_review.warnings
                reasons.append("broker review returned warnings")

        if not self.config.allow_auto_submit:
            reasons.append("manual execution approval required")

        return ExecutionPolicyDecision(approved=not reasons, reasons=reasons, checks=checks)

