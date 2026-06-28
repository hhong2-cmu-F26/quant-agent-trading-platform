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

Current status:

- agent OS primitives exist for registration, messages, tasks, and heartbeat
- worker primitives exist for processing durable pending tasks
- `quant.momentum_proposal` can turn bar data into an order proposal
- query APIs exist for agents, tasks, messages, proposals, broker orders, positions, and dashboard summary
- order proposal state machine exists with risk review and mock broker submission
- risk review can include durable account buying power and current position concentration
- SQLite persistence is the default API repository
- audit events are durable

## Phase 2: Quant Core

Add:

1. Market data ingestion.
2. Feature calculations.
3. Strategy signal generation.
4. Backtest runner.
5. Risk-adjusted strategy scoring.
6. Paper-trading replay engine.

Current status:

- durable price bar ingestion/query is implemented for local strategy inputs
- market data quality checks are implemented for duplicates, invalid OHLC, gaps, and stale bars
- deterministic feature snapshots are implemented in `market_data.py`
- a long-only momentum strategy is implemented in `strategy.py`
- long-only paper replay and risk-adjusted metrics are implemented in `paper.py`
- a long-only momentum backtest engine is implemented in `backtest.py`
- backtest records persist with config, metrics, and full result payload
- risk-adjusted strategy scorecards rank persisted backtests for research agents
- these modules intentionally have no FastAPI dependency so workers and tests can reuse them

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

Current status:

- `BrokerGateway` defines the broker boundary
- `RobinhoodMCPGateway` owns Robinhood MCP tool names and equity order payloads
- broker quote and tradability reads are available for market research and risk agents
- broker account and portfolio reads normalize into durable account/position state
- submitted orders can be cancelled through the broker gateway boundary
- `ExecutionPolicy` is now a final deterministic submit gate
- `ReconciliationService` updates proposals and positions only from broker-observed order snapshots
- the production MCP transport is still intentionally not wired

## Phase 4: Frontend

Add Next.js dashboard:

1. Portfolio and risk.
2. Agent task center.
3. Order proposal review.
4. Backtest reports.
5. Live order monitor.
6. Audit log.

Current status:

- `apps/web` contains the first Next.js operator dashboard
- dashboard sections cover account state, agents, tasks, proposals, broker orders, backtests, strategy scores, and audit events
- API access is isolated in a typed client so backend contracts stay visible

## Phase 5: Workers and Streaming

Add:

1. Portfolio sync worker.
2. Market data worker.
3. Backtest worker.
4. Agent task worker.
5. Event streaming via Redpanda/Kafka when needed.

Current status:

- `worker_service.py` provides a reusable polling loop around the durable agent task worker
- `portfolio.sync` persists broker-observed account and positions for risk checks
- `market_data.quote_snapshot` and `market_data.tradability_check` expose broker market checks as durable tasks
- worker service can run continuously or as a finite one-shot process for local checks and scheduled jobs
- dashboard can trigger a worker batch through `/worker/run-once` and a broker portfolio sync through `/broker/sync-portfolio`

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
