# Executable Build Plan

## Phase 1: Agent OS + Safe Order Flow

Build a minimal backend that supports:

1. Agent registration and role metadata.
2. Agent heartbeat for pending tasks/messages.
3. Order proposal creation from an agent or quant service.
4. Deterministic risk review.
5. Robinhood order review abstraction.
6. Approval state machine.
7. Execution abstraction with a mock adapter first.
8. Full audit trail.

This phase intentionally avoids direct live Robinhood placement until the ledger and risk flow are stable.

## Phase 2: Quant Core

Add:

1. Market data ingestion.
2. Feature calculations.
3. Strategy signal generation.
4. Backtest runner.
5. Risk-adjusted strategy scoring.
6. Paper-trading replay engine.

## Phase 3: Robinhood MCP Gateway

Add a dedicated service wrapping Robinhood Trading MCP:

1. `get_accounts`
2. `get_portfolio`
3. `get_equity_quotes`
4. `get_equity_tradability`
5. `review_equity_order`
6. `place_equity_order`
7. `cancel_equity_order`
8. order/fill reconciliation

All live execution must go through:

```text
proposal -> risk review -> Robinhood review -> policy approval -> place -> reconcile
```

## Phase 4: Frontend

Add Next.js dashboard:

1. Portfolio and risk.
2. Agent task center.
3. Order proposal review.
4. Backtest reports.
5. Live order monitor.
6. Audit log.

## Phase 5: Workers and Streaming

Add:

1. Portfolio sync worker.
2. Market data worker.
3. Backtest worker.
4. Agent task worker.
5. Event streaming via Redpanda/Kafka when needed.

## Agent Roles

- User Copilot Agent
- Market Research Agent
- Data Quality Agent
- Quant Research Agent
- Backtest Agent
- Risk Agent
- Execution Agent
- Monitoring Agent
- Options Agent later

