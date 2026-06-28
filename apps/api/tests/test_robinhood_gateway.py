import asyncio
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from trading_platform_api.broker import RobinhoodMCPGateway
from trading_platform_api.models import OrderProposal, OrderSide, OrderType


class FakeTransport:
    def __init__(self):
        self.calls = []

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name == "review_equity_order":
            return {"approved": True, "estimated_notional": 200.0, "warnings": []}
        return {"order_id": "rh_order_1", "status": "submitted"}


def test_robinhood_gateway_builds_review_and_place_payloads():
    transport = FakeTransport()
    gateway = RobinhoodMCPGateway(transport)
    proposal = OrderProposal(
        agent_id="agent_1",
        symbol="aapl",
        side=OrderSide.BUY,
        quantity=2,
        order_type=OrderType.LIMIT,
        limit_price=100,
    )

    review = asyncio.run(gateway.review_equity_order(proposal))
    receipt = asyncio.run(gateway.place_equity_order(proposal))

    assert review.approved is True
    assert review.estimated_notional == 200.0
    assert receipt.broker_order_id == "rh_order_1"
    assert transport.calls == [
        (
            "review_equity_order",
            {"symbol": "AAPL", "side": "buy", "quantity": 2.0, "order_type": "limit", "limit_price": 100.0},
        ),
        (
            "place_equity_order",
            {"symbol": "AAPL", "side": "buy", "quantity": 2.0, "order_type": "limit", "limit_price": 100.0},
        ),
    ]

