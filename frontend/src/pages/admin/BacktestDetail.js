import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { fetchBacktestDetail } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import LoadingSkeleton from "../../components/LoadingSkeleton";
import ErrorState from "../../components/ErrorState";
import Badge from "../../components/Badge";
import PnlText from "../../components/PnlText";
import Money from "../../components/Money";
import TradeTable from "../../components/TradeTable";
import Pagination from "../../components/Pagination";
import EquityCurveChart from "../../components/EquityCurveChart";
import { formatDateTime, formatWholePct, statusBadgeVariant } from "../../utils/format";

const POLL_INTERVAL_MS = 4000;
const PAGE_SIZE = 25;

/** Admin backtest results page — docs/design.md Section 4.13, with the
 * async queued -> running -> complete/failed pattern from Section 5.1. */
export default function BacktestDetail() {
  const { backtestId } = useParams();
  const { data, loading, error, refetch } = useFetch(() => fetchBacktestDetail(backtestId), [backtestId]);
  const [page, setPage] = useState(1);

  const isInFlight = data?.status === "queued" || data?.status === "running";

  useEffect(() => {
    if (!isInFlight) return;
    const interval = setInterval(refetch, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isInFlight, refetch]);

  if (loading) return <LoadingSkeleton rows={6} />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (!data) return null;

  if (isInFlight) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "var(--space-7)" }} aria-live="polite">
        <Badge variant={statusBadgeVariant(data.status)}>{data.status === "running" ? "Running" : "Queued"}</Badge>
        <p style={{ marginTop: "var(--space-4)" }}>Backtest in progress — this page will update automatically.</p>
      </div>
    );
  }

  if (data.status === "failed") {
    return (
      <div className="card" style={{ textAlign: "center", padding: "var(--space-7)" }}>
        <Badge variant="danger">Failed</Badge>
        <p style={{ marginTop: "var(--space-4)" }}>This backtest run failed.</p>
        <p className="text-muted">Reduce the date range or ticker subset and try again.</p>
      </div>
    );
  }

  const trades = data.backtest_trades || [];
  const totalTrades = trades.length;
  const start = (page - 1) * PAGE_SIZE;
  const pageTrades = trades.slice(start, start + PAGE_SIZE);

  return (
    <div>
      <p className="page-subtitle">
        BT-{data.id} · {data.start_date} to {data.end_date} · {data.tickers.length} tickers
      </p>
      <p className="page-subtitle">
        Starting capital: <Money value={data.starting_capital} /> · Completed {formatDateTime(data.finished_at)}
      </p>

      <div className="card" style={{ marginBottom: "var(--space-5)" }}>
        <h2 className="text-h2">Equity Curve</h2>
        <EquityCurveChart points={data.equity_curve} />
      </div>

      <div className="stat-grid" style={{ marginBottom: "var(--space-4)" }}>
        <div className="stat-card">
          <div className="stat-card-label">Total Return</div>
          <PnlText value={data.total_return_pct} pct />
          <div className="text-small text-muted">
            <PnlText value={data.total_return_abs} />
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Win Rate</div>
          <div className="stat-card-value">{data.win_rate ? formatWholePct(data.win_rate) : "—"}</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Total Trades</div>
          <div className="stat-card-value">{data.total_trades ?? "—"}</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Max Drawdown</div>
          <PnlText value={data.max_drawdown_pct} pct />
          <div className="text-small text-muted">
            <PnlText value={data.max_drawdown_abs} />
          </div>
        </div>
      </div>

      <div className="stat-card" style={{ maxWidth: 280, marginBottom: "var(--space-5)" }}>
        <div className="stat-card-label">Avg Holding Period</div>
        <div className="stat-card-value">{data.avg_holding_days ? `${Number(data.avg_holding_days).toFixed(1)}d` : "—"}</div>
      </div>

      <h2 className="text-h2">Trade Log ({totalTrades})</h2>
      <TradeTable trades={pageTrades} loading={false} error={null} />
      {totalTrades > PAGE_SIZE && (
        <Pagination page={page} pageSize={PAGE_SIZE} total={totalTrades} onPageChange={setPage} />
      )}
    </div>
  );
}
