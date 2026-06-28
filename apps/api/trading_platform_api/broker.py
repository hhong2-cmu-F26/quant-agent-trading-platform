from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from .models import (
    AccountState,
    BrokerOrderSnapshot,
    BrokerOrderStatus,
    BrokerReview,
    EquityQuote,
    EquityTradability,
    ExecutionReceipt,
    OrderProposal,
    OrderType,
    PortfolioPosition,
    TradabilityState,
)


class BrokerGateway(ABC):
    @abstractmethod
    async def get_account(self) -> AccountState:
        raise NotImplementedError

    @abstractmethod
    async def get_positions(self) -> list[PortfolioPosition]:
        raise NotImplementedError

    @abstractmethod
    async def get_equity_quotes(self, symbols: list[str]) -> list[EquityQuote]:
        raise NotImplementedError

    @abstractmethod
    async def get_equity_tradability(self, symbols: list[str]) -> list[EquityTradability]:
        raise NotImplementedError

    @abstractmethod
    async def review_equity_order(self, proposal: OrderProposal) -> BrokerReview:
        raise NotImplementedError

    @abstractmethod
    async def place_equity_order(self, proposal: OrderProposal) -> ExecutionReceipt:
        raise NotImplementedError

    @abstractmethod
    async def cancel_equity_order(self, broker_order_id: str) -> ExecutionReceipt:
        raise NotImplementedError

    @abstractmethod
    async def get_equity_order(self, proposal: OrderProposal) -> BrokerOrderSnapshot:
        raise NotImplementedError


class MockRobinhoodGateway(BrokerGateway):
    """Development adapter with Robinhood-like review/place boundaries."""

    def __init__(
        self,
        account: AccountState | None = None,
        positions: list[PortfolioPosition] | None = None,
        order_snapshots: dict[str, BrokerOrderSnapshot] | None = None,
    ):
        self.account = account or AccountState(buying_power=100_000, cash=100_000, equity=100_000)
        self.positions = positions or []
        self.order_snapshots = order_snapshots or {}

    async def get_account(self) -> AccountState:
        return self.account

    async def get_positions(self) -> list[PortfolioPosition]:
        return self.positions

    async def get_equity_quotes(self, symbols: list[str]) -> list[EquityQuote]:
        return [
            EquityQuote(
                symbol=symbol.strip().upper(),
                bid_price=99.95,
                ask_price=100.05,
                last_trade_price=100.0,
                previous_close=99.5,
                raw={"adapter": "mock_robinhood"},
            )
            for symbol in self._normalize_symbols(symbols)
        ]

    async def get_equity_tradability(self, symbols: list[str]) -> list[EquityTradability]:
        return [
            EquityTradability(
                symbol=symbol,
                state=TradabilityState.NOT_TRADABLE if symbol in {"ZZZZ"} else TradabilityState.TRADABLE,
                reason="mock unavailable symbol" if symbol in {"ZZZZ"} else None,
                raw={"adapter": "mock_robinhood"},
            )
            for symbol in self._normalize_symbols(symbols)
        ]

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

    async def cancel_equity_order(self, broker_order_id: str) -> ExecutionReceipt:
        return ExecutionReceipt(
            broker_order_id=broker_order_id,
            status="cancelled",
            raw={"adapter": "mock_robinhood"},
        )

    async def get_equity_order(self, proposal: OrderProposal) -> BrokerOrderSnapshot:
        if not proposal.execution:
            raise ValueError("proposal has no broker order")
        snapshot = self.order_snapshots.get(proposal.execution.broker_order_id)
        if snapshot:
            return snapshot
        return BrokerOrderSnapshot(
            broker_order_id=proposal.execution.broker_order_id,
            proposal_id=proposal.id,
            symbol=proposal.symbol,
            side=proposal.side,
            status=BrokerOrderStatus.SUBMITTED,
            submitted_quantity=proposal.quantity,
            filled_quantity=0,
            raw={"adapter": "mock_robinhood"},
        )

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        normalized = []
        for symbol in symbols:
            parsed = symbol.strip().upper()
            if parsed:
                normalized.append(parsed)
        return normalized


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

    async def get_account(self) -> AccountState:
        raw = await self.transport.call_tool("get_accounts", {})
        payload = self._first_payload(raw, "accounts")
        return AccountState(
            buying_power=self._float(payload, "buying_power", "buyingPower"),
            cash=self._float(payload, "cash", "cash_balance", "cashBalance"),
            equity=self._float(payload, "equity", "portfolio_value", "portfolioValue"),
        )

    async def get_positions(self) -> list[PortfolioPosition]:
        raw = await self.transport.call_tool("get_portfolio", {})
        items = raw.get("positions") or raw.get("results") or raw.get("portfolio") or []
        if isinstance(items, dict):
            items = items.get("positions") or items.get("results") or []
        positions: list[PortfolioPosition] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or item.get("instrument_symbol") or item.get("ticker") or "").strip()
            if not symbol:
                continue
            positions.append(
                PortfolioPosition(
                    symbol=symbol.upper(),
                    quantity=self._float(item, "quantity", "shares", "qty"),
                    average_price=self._float(item, "average_price", "average_buy_price", "avgPrice"),
                )
            )
        return positions

    async def get_equity_quotes(self, symbols: list[str]) -> list[EquityQuote]:
        normalized = self._normalize_symbols(symbols)
        raw = await self.transport.call_tool("get_equity_quotes", {"symbols": normalized})
        items = raw.get("quotes") or raw.get("results") or raw.get("items") or []
        if isinstance(items, dict):
            items = [items]
        quotes: list[EquityQuote] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
            if not symbol:
                continue
            quotes.append(
                EquityQuote(
                    symbol=symbol,
                    bid_price=self._optional_float(item, "bid_price", "bid", "bidPrice"),
                    ask_price=self._optional_float(item, "ask_price", "ask", "askPrice"),
                    last_trade_price=self._optional_float(item, "last_trade_price", "last", "lastPrice", "mark_price"),
                    previous_close=self._optional_float(item, "previous_close", "previousClose"),
                    raw=item,
                )
            )
        return quotes

    async def get_equity_tradability(self, symbols: list[str]) -> list[EquityTradability]:
        normalized = self._normalize_symbols(symbols)
        raw = await self.transport.call_tool("get_equity_tradability", {"symbols": normalized})
        items = raw.get("tradability") or raw.get("results") or raw.get("items") or []
        if isinstance(items, dict):
            items = [items]
        results: list[EquityTradability] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
            if not symbol:
                continue
            raw_state = str(item.get("state") or item.get("tradability") or item.get("status") or "").lower()
            tradable = item.get("tradable")
            state = self._tradability_state(raw_state, tradable)
            results.append(
                EquityTradability(
                    symbol=symbol,
                    state=state,
                    reason=item.get("reason") or item.get("message"),
                    raw=item,
                )
            )
        return results

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

    async def cancel_equity_order(self, broker_order_id: str) -> ExecutionReceipt:
        raw = await self.transport.call_tool("cancel_equity_order", {"order_id": broker_order_id})
        return ExecutionReceipt(
            broker_order_id=str(raw.get("order_id") or raw.get("id") or raw.get("broker_order_id") or broker_order_id),
            status=str(raw.get("status") or "cancelled"),
            raw=raw,
        )

    async def get_equity_order(self, proposal: OrderProposal) -> BrokerOrderSnapshot:
        if not proposal.execution:
            raise ValueError("proposal has no broker order")
        raw = await self.transport.call_tool("get_order", {"order_id": proposal.execution.broker_order_id})
        status = self._broker_order_status(str(raw.get("status") or raw.get("state") or "submitted"))
        return BrokerOrderSnapshot(
            broker_order_id=str(raw.get("order_id") or raw.get("id") or raw.get("broker_order_id") or proposal.execution.broker_order_id),
            proposal_id=proposal.id,
            symbol=str(raw.get("symbol") or proposal.symbol).upper(),
            side=proposal.side,
            status=status,
            submitted_quantity=self._optional_float(raw, "submitted_quantity", "quantity", "qty") or proposal.quantity,
            filled_quantity=self._optional_float(raw, "filled_quantity", "filled_qty", "cumulative_quantity") or 0.0,
            average_fill_price=self._optional_float(raw, "average_fill_price", "avg_fill_price", "average_price"),
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

    def _first_payload(self, raw: dict[str, Any], list_key: str) -> dict[str, Any]:
        items = raw.get(list_key)
        if isinstance(items, list) and items:
            first = items[0]
            return first if isinstance(first, dict) else {}
        return raw

    def _float(self, payload: dict[str, Any], *keys: str) -> float:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return float(value)
        return 0.0

    def _optional_float(self, payload: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return float(value)
        return None

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        normalized = []
        for symbol in symbols:
            parsed = symbol.strip().upper()
            if parsed:
                normalized.append(parsed)
        if not normalized:
            raise ValueError("at least one symbol is required")
        return normalized

    def _tradability_state(self, raw_state: str, tradable: Any) -> TradabilityState:
        if isinstance(tradable, bool):
            return TradabilityState.TRADABLE if tradable else TradabilityState.NOT_TRADABLE
        if raw_state in {"tradable", "tradeable", "active", "ok"}:
            return TradabilityState.TRADABLE
        if raw_state in {"not_tradable", "not_tradeable", "inactive", "halted", "blocked"}:
            return TradabilityState.NOT_TRADABLE
        return TradabilityState.UNKNOWN

    def _broker_order_status(self, raw_status: str) -> BrokerOrderStatus:
        normalized = raw_status.lower()
        if normalized in {"filled", "executed"}:
            return BrokerOrderStatus.FILLED
        if normalized in {"partially_filled", "partial", "part_filled"}:
            return BrokerOrderStatus.PARTIALLY_FILLED
        if normalized in {"cancelled", "canceled"}:
            return BrokerOrderStatus.CANCELLED
        if normalized in {"rejected"}:
            return BrokerOrderStatus.REJECTED
        if normalized in {"failed", "error"}:
            return BrokerOrderStatus.FAILED
        if normalized in {"pending", "queued"}:
            return BrokerOrderStatus.PENDING
        return BrokerOrderStatus.SUBMITTED
