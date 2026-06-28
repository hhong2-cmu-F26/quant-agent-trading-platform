# Quant Agent Trading Platform

LLM-assisted quant trading platform with a deterministic trading core and a Robinhood Agentic Trading execution boundary.

The design borrows the useful "agent operating system around trading" ideas from HKUDS/AI-Trader:

- agent skill definitions
- registration and identity
- heartbeat/task polling
- immutable signal/order records
- server-side price and risk authority
- background workers
- replayable paper-trading and scoring

It does not copy AI-Trader's simulated execution model for live trading. Live positions must be reconciled from Robinhood order/fill truth.

## First Slice

This repo currently scaffolds the backend safety path:

```text
agent task
-> order proposal
-> deterministic risk review
-> Robinhood order review abstraction
-> approval state
-> execution abstraction
-> audit trail
```

It also includes the first quant evaluation slice:

```text
price bars
-> deterministic feature snapshot
-> long-only momentum proposal
-> paper replay
-> risk-adjusted metrics
```

LLM agents may research, propose, and explain. They do not get final direct authority to place live orders.

## Layout

```text
apps/api/                 FastAPI backend core
docs/                     architecture and execution plan
agent_skills/             role-specific agent operating instructions
```

## Run Backend

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn trading_platform_api.main:app --reload
```
