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
-> broker cancellation boundary
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
apps/web/                 Next.js operator dashboard
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

By default the API stores durable state in:

```text
apps/api/data/trading_platform.db
```

Override it with:

```bash
set TRADING_PLATFORM_DB_PATH=C:\path\to\platform.db
```

Allowed browser origins default to `http://localhost:3000` and `http://127.0.0.1:3000`. Override them with:

```bash
set TRADING_PLATFORM_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## Run Worker

```bash
cd apps/api
python -m trading_platform_api.worker_service
```

For a one-shot batch useful in local checks:

```bash
python -m trading_platform_api.worker_service --max-iterations 1 --poll-interval 0
```

The durable worker understands these task kinds:

```text
portfolio.sync
broker.reconcile_submitted
market_data.quote_snapshot
market_data.tradability_check
market_data.quality_check
quant.momentum_proposal
backtest.momentum
strategy.score_backtests
```

## Run Frontend

```bash
cd apps/web
npm install
npm run dev
```

The dashboard expects the API at:

```text
http://localhost:8000
```

Override it with:

```bash
set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```
