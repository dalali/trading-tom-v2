import React, { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchBacktests } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import LoadingSkeleton from "../../components/LoadingSkeleton";
import ErrorState from "../../components/ErrorState";
import EmptyState from "../../components/EmptyState";
import Badge from "../../components/Badge";
import PnlText from "../../components/PnlText";
import { adminBacktestDetailPath, PATHS } from "../../routes/paths";
import { formatDateTime, formatWholePct, statusBadgeVariant } from "../../utils/format";

const POLL_INTERVAL_MS = 4000;

/** Admin backtest run list — docs/design.md Section 4.12. Polls while
 * any run is queued/running (Section 5.1's shared status pattern). */
export default function BacktestList() {
  const navigate = useNavigate();
  const { data, loading, error, refetch } = useFetch(() => fetchBacktests({ page: 1, page_size: 20 }), []);

  const hasInFlight = data?.items?.some((r) => r.status === "queued" || r.status === "running");

  useEffect(() => {
    if (!hasInFlight) return;
    const interval = setInterval(refetch, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [hasInFlight, refetch]);

  return (
    <div>
      <div className="card-header" style={{ marginBottom: "var(--space-4)" }}>
        <h1 className="text-h1" style={{ margin: 0 }}>
          Backtests
        </h1>
        <Link to={PATHS.adminBacktestNew} className="btn btn-primary" style={{ textDecoration: "none" }}>
          + New Backtest
        </Link>
      </div>

      {loading && <LoadingSkeleton rows={5} />}
      {!loading && error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && data && data.items.length === 0 && (
        <EmptyState
          title="No backtests have been run yet."
          description="Evaluate the strategy against historical data."
          action={
            <Link to={PATHS.adminBacktestNew} className="btn btn-primary" style={{ textDecoration: "none" }}>
              + New Backtest
            </Link>
          }
        />
      )}

      {!loading && !error && data && data.items.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Submitted</th>
                <th>Range</th>
                <th className="col-num">Tickers</th>
                <th className="col-center">Status</th>
                <th className="col-num">Return</th>
                <th className="col-num">Win Rate</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((run) => (
                <tr key={run.id} className="clickable" onClick={() => navigate(adminBacktestDetailPath(run.id))}>
                  <td>BT-{run.id}</td>
                  <td>{formatDateTime(run.created_at)}</td>
                  <td>
                    {run.start_date} — {run.end_date}
                  </td>
                  <td className="col-num">{run.tickers.length} tkrs</td>
                  <td className="col-center">
                    <Badge variant={statusBadgeVariant(run.status)}>
                      {run.status.charAt(0).toUpperCase() + run.status.slice(1)}
                    </Badge>
                  </td>
                  <td className="col-num">
                    {run.status === "complete" ? <PnlText value={run.total_return_pct} pct /> : "—"}
                  </td>
                  <td className="col-num">{run.status === "complete" && run.win_rate ? formatWholePct(run.win_rate) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
