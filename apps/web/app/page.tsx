"use client";

import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  ClipboardCheck,
  LineChart,
  ListChecks,
  RefreshCw,
  RefreshCcw,
  ShieldCheck,
  TerminalSquare,
  WalletCards
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  loadDashboardData,
  runWorkerOnce,
  syncPortfolio,
  type DashboardSummary,
  type PortfolioSyncResult,
  type WorkerRunSummary
} from "../lib/api";

type DashboardData = Awaited<ReturnType<typeof loadDashboardData>>;

const tabs = ["Operations", "Orders", "Research", "Audit"] as const;
type Tab = (typeof tabs)[number];

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("Operations");
  const [updatedAt, setUpdatedAt] = useState<string>("");
  const [workerRun, setWorkerRun] = useState<WorkerRunSummary | null>(null);
  const [workerRunning, setWorkerRunning] = useState(false);
  const [portfolioSync, setPortfolioSync] = useState<PortfolioSyncResult | null>(null);
  const [syncRunning, setSyncRunning] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const nextData = await loadDashboardData();
      setData(nextData);
      setUpdatedAt(new Date().toLocaleTimeString());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const summary = data?.summary;
  const riskState = useMemo(() => riskLabel(summary), [summary]);

  async function runWorker() {
    setWorkerRunning(true);
    setError(null);
    try {
      const summary = await runWorkerOnce(10);
      setWorkerRun(summary);
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to run worker");
    } finally {
      setWorkerRunning(false);
    }
  }

  async function runPortfolioSync() {
    setSyncRunning(true);
    setError(null);
    try {
      const result = await syncPortfolio();
      setPortfolioSync(result);
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to sync portfolio");
    } finally {
      setSyncRunning(false);
    }
  }

  return (
    <main>
      <header className="shell header">
        <div>
          <p className="eyebrow">Agentic Quant Trading</p>
          <h1>Command Center</h1>
        </div>
        <div className="headerActions">
          <span className="statusText">{updatedAt ? `Updated ${updatedAt}` : "Waiting for API"}</span>
          <button className="iconButton" onClick={refresh} aria-label="Refresh dashboard" title="Refresh dashboard">
            <RefreshCcw size={18} />
          </button>
        </div>
      </header>

      <section className="shell statusBand" aria-label="Platform status">
        <Metric icon={<WalletCards />} label="Equity" value={money(summary?.account.equity)} detail={`Cash ${money(summary?.account.cash)}`} />
        <Metric icon={<ShieldCheck />} label="Buying Power" value={money(summary?.account.buying_power)} detail={riskState} tone={riskState === "Constrained" ? "warn" : "ok"} />
        <Metric icon={<Bot />} label="Agents" value={summary?.agent_count ?? 0} detail={`${summary?.pending_task_count ?? 0} pending tasks`} />
        <Metric icon={<ListChecks />} label="Orders" value={summary?.proposal_count ?? 0} detail={`${summary?.open_position_count ?? 0} open positions`} />
        <Metric icon={<BarChart3 />} label="Backtests" value={summary?.backtest_count ?? 0} detail={`${data?.scores.length ?? 0} scored`} />
      </section>

      <section className="shell toolbar">
        <div className="tabs" role="tablist" aria-label="Dashboard sections">
          {tabs.map((tab) => (
            <button key={tab} className={tab === activeTab ? "tab active" : "tab"} onClick={() => setActiveTab(tab)} type="button">
              {tab}
            </button>
          ))}
        </div>
        {loading && <span className="statusText">Loading</span>}
        <button className="actionButton" onClick={runWorker} disabled={workerRunning} type="button">
          <TerminalSquare size={16} />
          {workerRunning ? "Running" : "Run Worker"}
        </button>
        <button className="actionButton secondary" onClick={runPortfolioSync} disabled={syncRunning} type="button">
          <RefreshCw size={16} />
          {syncRunning ? "Syncing" : "Sync Portfolio"}
        </button>
        {workerRun && (
          <span className="statusText">
            Worker {workerRun.processed} processed, {workerRun.failed} failed
          </span>
        )}
        {portfolioSync && (
          <span className="statusText">
            Portfolio {portfolioSync.position_count} positions
          </span>
        )}
        {error && (
          <span className="errorText">
            <AlertTriangle size={16} /> {error}
          </span>
        )}
      </section>

      {data && (
        <section className="shell workspace">
          {activeTab === "Operations" && <Operations data={data} />}
          {activeTab === "Orders" && <Orders data={data} />}
          {activeTab === "Research" && <Research data={data} />}
          {activeTab === "Audit" && <Audit data={data} />}
        </section>
      )}
    </main>
  );
}

function Operations({ data }: { data: DashboardData }) {
  return (
    <div className="grid two">
      <Panel title="Agent Tasks" icon={<TerminalSquare />}>
        <table>
          <thead>
            <tr>
              <th>Kind</th>
              <th>Status</th>
              <th>Agent</th>
              <th>Completed</th>
            </tr>
          </thead>
          <tbody>
            {data.tasks.map((task) => (
              <tr key={task.id}>
                <td>{task.kind}</td>
                <td><Badge value={task.status} /></td>
                <td>{shortId(task.agent_id)}</td>
                <td>{time(task.completed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Agents" icon={<Bot />}>
        <div className="list">
          {data.agents.map((agent) => (
            <article className="rowCard" key={agent.id}>
              <strong>{agent.name}</strong>
              <span>{agent.role}</span>
              <code>{shortId(agent.id)}</code>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Orders({ data }: { data: DashboardData }) {
  return (
    <div className="grid two">
      <Panel title="Order Proposals" icon={<ClipboardCheck />}>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>Qty</th>
              <th>Status</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {data.proposals.map((proposal) => (
              <tr key={proposal.id}>
                <td>{proposal.symbol}</td>
                <td>{proposal.side}</td>
                <td>{number(proposal.quantity)}</td>
                <td><Badge value={proposal.status} /></td>
                <td>{proposal.risk ? (proposal.risk.approved ? "approved" : "blocked") : "pending"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Broker Orders" icon={<Activity />}>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Status</th>
              <th>Filled</th>
              <th>Avg Fill</th>
            </tr>
          </thead>
          <tbody>
            {data.brokerOrders.map((order) => (
              <tr key={order.broker_order_id}>
                <td>{order.symbol}</td>
                <td><Badge value={order.status} /></td>
                <td>{number(order.filled_quantity)} / {number(order.submitted_quantity)}</td>
                <td>{money(order.average_fill_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

function Research({ data }: { data: DashboardData }) {
  return (
    <div className="grid two">
      <Panel title="Strategy Scores" icon={<LineChart />}>
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Strategy</th>
              <th>Symbol</th>
              <th>Score</th>
              <th>Return</th>
              <th>Drawdown</th>
            </tr>
          </thead>
          <tbody>
            {data.scores.map((score) => (
              <tr key={score.backtest_id}>
                <td>{score.rank}</td>
                <td>{score.strategy_id}</td>
                <td>{score.symbol}</td>
                <td>{score.score.toFixed(2)}</td>
                <td>{score.return_pct.toFixed(2)}%</td>
                <td>{score.max_drawdown_pct.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Backtest Records" icon={<BarChart3 />}>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Strategy</th>
              <th>Trades</th>
              <th>Return</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {data.backtests.map((record) => (
              <tr key={record.id}>
                <td>{record.symbol}</td>
                <td>{record.strategy_id}</td>
                <td>{metric(record.metrics.trade_count)}</td>
                <td>{metric(record.metrics.return_pct)}%</td>
                <td>{time(record.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

function Audit({ data }: { data: DashboardData }) {
  return (
    <Panel title="Audit Log" icon={<Activity />}>
      <table>
        <thead>
          <tr>
            <th>Event</th>
            <th>Payload</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {data.audit.map((event, index) => (
            <tr key={`${event.event_type}-${index}`}>
              <td>{event.event_type}</td>
              <td><code>{JSON.stringify(event.payload)}</code></td>
              <td>{time(event.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function Metric({ icon, label, value, detail, tone }: { icon: React.ReactNode; label: string; value: React.ReactNode; detail: string; tone?: "ok" | "warn" }) {
  return (
    <article className={`metric ${tone ?? ""}`}>
      <div className="metricIcon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel">
      <h2>{icon}{title}</h2>
      {children}
    </section>
  );
}

function Badge({ value }: { value: string }) {
  return <span className={`badge ${value.replaceAll("_", "-")}`}>{value}</span>;
}

function riskLabel(summary?: DashboardSummary) {
  if (!summary) return "Unknown";
  if (summary.account.buying_power <= 0) return "Constrained";
  if (summary.running_task_count > 5) return "Busy";
  return "Ready";
}

function money(value?: number | null) {
  if (typeof value !== "number") return "$0";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function number(value?: number | null) {
  if (typeof value !== "number") return "0";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

function metric(value: unknown) {
  return typeof value === "number" ? value.toFixed(2).replace(/\.00$/, "") : "0";
}

function shortId(value: string) {
  return value.length > 14 ? `${value.slice(0, 10)}...` : value;
}

function time(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}
