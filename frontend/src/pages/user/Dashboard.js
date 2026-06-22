import React from "react";
import { Link } from "react-router-dom";
import { fetchMyAccount, fetchMyPositions, fetchMyTrades } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import StatCard from "../../components/StatCard";
import Money from "../../components/Money";
import PnlText from "../../components/PnlText";
import ReasonBadge from "../../components/ReasonBadge";
import LoadingSkeleton from "../../components/LoadingSkeleton";
import ErrorState from "../../components/ErrorState";
import { PATHS } from "../../routes/paths";
import { formatDate, formatDateTime } from "../../utils/format";

/** Regular user dashboard — docs/design.md Section 4.2. */
export default function Dashboard() {
  const account = useFetch(fetchMyAccount, []);
  const positions = useFetch(fetchMyPositions, []);
  const trades = useFetch(() => fetchMyTrades({ page: 1, page_size: 5 }), []);

  const loading = account.loading || positions.loading;

  return (
    <div>
      <h1 className="text-h1 page-title">Dashboard</h1>

      {!loading && account.data && (
        <p className="page-subtitle">
          As of last engine run: {formatDateTime(account.data.as_of)}
        </p>
      )}

      {loading && <LoadingSkeleton rows={5} />}

      {!loading && account.error && (
        <ErrorState message={`Couldn't load your account. ${account.error}`} onRetry={account.refetch} />
      )}

      {!loading && account.data && Number(account.data.total_value) === 0 && (
        <ZeroState account={account.data} />
      )}

      {!loading && account.data && Number(account.data.total_value) !== 0 && (
        <>
          <div className="stat-grid" style={{ marginBottom: "var(--space-4)" }}>
            <StatCard label="Total Value" value={<Money value={account.data.total_value} />} />
            <StatCard label="Cash Balance" value={<Money value={account.data.cash_balance} />} />
            <StatCard label="Equity Value" value={<Money value={account.data.equity_value} />} />
          </div>

          <div className="stat-grid-2" style={{ marginBottom: "var(--space-5)" }}>
            <div className="stat-card">
              <div className="stat-card-label">Realized P&amp;L (lifetime)</div>
              <PnlText value={account.data.realized_pnl} />
            </div>
            <div className="stat-card">
              <div className="stat-card-label">Unrealized P&amp;L (open)</div>
              <PnlText value={account.data.unrealized_pnl} />
            </div>
          </div>

          <div className="card" style={{ marginBottom: "var(--space-4)" }}>
            <div className="card-header">
              <h2 className="text-h2" style={{ margin: 0 }}>
                Open Positions ({positions.data?.length || 0})
              </h2>
              <Link to={PATHS.positions}>View all →</Link>
            </div>
            <PositionsPreview positions={positions.data} loading={positions.loading} error={positions.error} />
          </div>

          <div className="card">
            <div className="card-header">
              <h2 className="text-h2" style={{ margin: 0 }}>
                Recent Trades
              </h2>
              <Link to={PATHS.trades}>View all →</Link>
            </div>
            <RecentTradesPreview trades={trades.data?.items} loading={trades.loading} error={trades.error} />
          </div>
        </>
      )}
    </div>
  );
}

function ZeroState({ account }) {
  return (
    <div className="card" style={{ textAlign: "center", padding: "var(--space-7)" }}>
      <div style={{ fontSize: 40 }} aria-hidden="true">
        🪙
      </div>
      <h2 className="text-h2">You're not funded yet</h2>
      <p className="text-muted">
        Your account balance is $0.00. The trading engine only trades on funded accounts. Ask your admin to load
        virtual cash into your account to get started.
      </p>
      <p>
        Cash: <Money value={account.cash_balance} /> &nbsp; Equity: <Money value={account.equity_value} /> &nbsp;
        Total: <Money value={account.total_value} />
      </p>
    </div>
  );
}

function PositionsPreview({ positions, loading, error }) {
  if (loading) return <LoadingSkeleton rows={3} />;
  if (error) return <ErrorState message={error} />;
  if (!positions || positions.length === 0) {
    return <p className="text-muted">No open positions right now.</p>;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th className="col-num">Qty</th>
            <th className="col-num">Entry</th>
            <th className="col-num">Current</th>
            <th className="col-num">Days</th>
            <th className="col-num">Unreal. P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {positions.slice(0, 5).map((p) => (
            <tr key={p.ticker}>
              <td className="ticker-cell">{p.ticker}</td>
              <td className="col-num">{p.quantity}</td>
              <td className="col-num">
                <Money value={p.entry_price} />
              </td>
              <td className="col-num">
                <Money value={p.current_price} />
              </td>
              <td className="col-num">{p.days_held}d</td>
              <td className="col-num">
                <PnlText value={p.unrealized_pnl_abs} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecentTradesPreview({ trades, loading, error }) {
  if (loading) return <LoadingSkeleton rows={3} />;
  if (error) return <ErrorState message={error} />;
  if (!trades || trades.length === 0) {
    return <p className="text-muted">No trades yet. Check back after the next engine run.</p>;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Side</th>
            <th>Ticker</th>
            <th className="col-num">Qty</th>
            <th className="col-num">Price</th>
            <th className="col-center">Reason</th>
            <th className="col-num">P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id}>
              <td>{formatDate(t.bar_date)}</td>
              <td>{t.side}</td>
              <td className="ticker-cell">{t.ticker}</td>
              <td className="col-num">{t.quantity}</td>
              <td className="col-num">
                <Money value={t.price} />
              </td>
              <td className="col-center">
                <ReasonBadge reason={t.signal_reason} />
              </td>
              <td className="col-num">
                <PnlText value={t.realized_pnl} naLabel="—" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
