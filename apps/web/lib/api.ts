export type Agent = {
  id: string;
  name: string;
  role: string;
  created_at: string;
};

export type AgentTask = {
  id: string;
  agent_id: string;
  kind: string;
  status: string;
  payload: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
};

export type AccountState = {
  buying_power: number;
  cash: number;
  equity: number;
  updated_at: string;
};

export type PortfolioPosition = {
  symbol: string;
  quantity: number;
  average_price: number;
  updated_at: string;
};

export type OrderProposal = {
  id: string;
  agent_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  order_type: "market" | "limit";
  limit_price?: number | null;
  rationale: string;
  strategy_id?: string | null;
  status: string;
  risk?: {
    approved: boolean;
    reasons: string[];
    checks: Record<string, unknown>;
  } | null;
  broker_review?: {
    approved: boolean;
    warnings: string[];
    estimated_notional?: number | null;
  } | null;
  created_at: string;
  updated_at: string;
};

export type BacktestRecord = {
  id: string;
  strategy_id: string;
  symbol: string;
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
  created_at: string;
};

export type BrokerOrder = {
  broker_order_id: string;
  proposal_id: string;
  symbol: string;
  side: "buy" | "sell";
  status: string;
  submitted_quantity: number;
  filled_quantity: number;
  average_fill_price?: number | null;
  observed_at: string;
};

export type AuditEvent = {
  id?: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type DashboardSummary = {
  account: AccountState;
  agent_count: number;
  pending_task_count: number;
  running_task_count: number;
  proposal_count: number;
  backtest_count: number;
  open_position_count: number;
  recent_proposals: OrderProposal[];
  positions: PortfolioPosition[];
};

export type StrategyScore = {
  backtest_id: string;
  strategy_id: string;
  symbol: string;
  score: number;
  rank: number;
  return_pct: number;
  max_drawdown_pct: number;
  trade_count: number;
  rejected_trade_count: number;
  reasons: string[];
};

export type WorkerRunSummary = {
  processed: number;
  succeeded: number;
  failed: number;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function loadDashboardData() {
  const [summary, agents, tasks, proposals, backtests, brokerOrders, audit, scores] = await Promise.all([
    getJson<DashboardSummary>("/dashboard/summary"),
    getJson<{ agents: Agent[] }>("/agents"),
    getJson<{ tasks: AgentTask[] }>("/agents/tasks?limit=25"),
    getJson<{ proposals: OrderProposal[] }>("/orders/proposals?limit=25"),
    getJson<{ backtests: BacktestRecord[] }>("/backtests?limit=25"),
    getJson<{ broker_orders: BrokerOrder[] }>("/broker/orders?limit=25"),
    getJson<{ events: AuditEvent[] }>("/audit"),
    postJson<{ scores: StrategyScore[] }>("/backtests/scores", { limit: 10 })
  ]);

  return {
    summary,
    agents: agents.agents,
    tasks: tasks.tasks,
    proposals: proposals.proposals,
    backtests: backtests.backtests,
    brokerOrders: brokerOrders.broker_orders,
    audit: audit.events.slice(0, 25),
    scores: scores.scores
  };
}

export async function runWorkerOnce(limit = 10) {
  return postJson<WorkerRunSummary>(`/worker/run-once?limit=${limit}`, {});
}
