from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from .models import BrokerReview, ExecutionReceipt, OrderProposal, OrderType


class BrokerGateway(ABC):
    @abstractmethod
    async def review_equity_order(self, proposal: OrderProposal) -> BrokerReview:
        raise NotImplementedError

    @abstractmethod
    async def place_equity_order(self, proposal: OrderProposal) -> ExecutionReceipt:
        raise NotImplementedError


class MockRobinhoodGateway(BrokerGateway):
    """Development adapter with Robinhood-like review/place boundaries."""

    async def review_equity_order(self, proposal: OrderProposal) -> BrokerReview:
        estimated_notional = None
        warnings: list[str] = []
        if proposal.limit_price is not None:
            estimated_notional = proposal.limit_price * proposal.quantity
        if proposal.symbol.upper() in {"GME", "AMC"}:
            warnings.append("high volatility symbol")
        return BrokerReview(
            approved=True,
            warnings=warnings,
            estimated_notional=estimated_notional,
            raw={"adapter": "mock_robinhood"},
        )

    async def place_equity_order(self, proposal: OrderProposal) -> ExecutionReceipt:
        return ExecutionReceipt(
            broker_order_id=f"mock_{proposal.id}",
            status="submitted",
            raw={"adapter": "mock_robinhood"},
        )


class MCPTransport(Protocol):
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class RobinhoodMCPGateway(BrokerGateway):
    """Robinhood Trading MCP adapter skeleton.

    This class owns Robinhood-specific tool names and payload shapes. It expects
    a transport that can call MCP tools against Robinhood's Trading MCP server.
    """

    MCP_ENDPOINT = "https://agent.robinhood.com/mcp/trading"

    def __init__(self, transport: MCPTransport):
        self.transport = transport

    async def review_equity_order(self, proposal: OrderProposal) -> BrokerReview:
        raw = await self.transport.call_tool("review_equity_order", self._equity_order_args(proposal))
        return self._parse_review(raw)

    async def place_equity_order(self, proposal: OrderProposal) -> ExecutionReceipt:
        raw = await self.transport.call_tool("place_equity_order", self._equity_order_args(proposal))
        broker_order_id = str(
            raw.get("order_id")
            or raw.get("id")
            or raw.get("broker_order_id")
            or f"rh_pending_{proposal.id}"
        )
        return ExecutionReceipt(
            broker_order_id=broker_order_id,
            status=str(raw.get("status") or "submitted"),
            raw=raw,
        )

    def _equity_order_args(self, proposal: OrderProposal) -> dict[str, Any]:
        if proposal.order_type == OrderType.LIMIT and proposal.limit_price is None:
            raise ValueError("limit orders require limit_price")
        args: dict[str, Any] = {
            "symbol": proposal.symbol.upper(),
            "side": proposal.side.value,
            "quantity": proposal.quantity,
            "order_type": proposal.order_type.value,
        }
        if proposal.limit_price is not None:
            args["limit_price"] = proposal.limit_price
        return args

    def _parse_review(self, raw: dict[str, Any]) -> BrokerReview:
        warnings = raw.get("warnings") or raw.get("messages") or []
        if isinstance(warnings, str):
            warnings = [warnings]
        estimated_notional = raw.get("estimated_notional") or raw.get("notional")
        return BrokerReview(
            approved=bool(raw.get("approved", raw.get("ok", True))),
            warnings=[str(warning) for warning in warnings],
            estimated_notional=float(estimated_notional) if estimated_notional is not None else None,
            raw=raw,
        )

