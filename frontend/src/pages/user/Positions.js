import React from "react";
import { Link } from "react-router-dom";
import { fetchMyPositions } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import Money from "../../components/Money";
import PnlText from "../../components/PnlText";
import LoadingSkeleton from "../../components/LoadingSkeleton";
import ErrorState from "../../components/ErrorState";
import EmptyState from "../../components/EmptyState";
import { PATHS } from "../../routes/paths";
import { formatDate } from "../../utils/format";

const MAX_POSITIONS = 5;

/** Open positions detail — docs/design.md Section 4.4. */
export default function Positions() {
  const { data: positions, loading, error, refetch } = useFetch(fetchMyPositions, []);

  return (
    <div>
      <h1 className="text-h1 page-title">
        Open Positions {!loading && positions && `(${positions.length} of ${MAX_POSITIONS} max)`}
      </h1>

      {loading && <LoadingSkeleton rows={5} />}
      {!loading && error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && positions && positions.length === 0 && (
        <EmptyState
          title="You have no open positions right now."
          description="Check your Trade History to see past trades."
          action={
            <Link to={PATHS.trades} className="btn btn-secondary" style={{ textDecoration: "none" }}>
              Go to Trade History
            </Link>
          }
        />
      )}

      {!loading && !error && positions && positions.length > 0 && (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th className="col-num">Qty</th>
                  <th className="col-num">Entry Price</th>
                  <th>Entry Date</th>
                  <th className="col-num">Days Held</th>
                  <th className="col-num">Current Price</th>
                  <th className="col-num">Unreal. P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.ticker}>
                    <td className="ticker-cell">{p.ticker}</td>
                    <td className="col-num">{p.quantity}</td>
                    <td className="col-num">
                      <Money value={p.entry_price} />
                    </td>
                    <td>{formatDate(p.entry_date)}</td>
                    <td className="col-num">{p.days_held}d</td>
                    <td className="col-num">
                      <Money value={p.current_price} />
                    </td>
                    <td className="col-num">
                      <PnlText value={p.unrealized_pnl_abs} />
                      <div className="text-small text-muted">
                        <PnlText value={p.unrealized_pnl_pct} pct />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="banner banner-info" style={{ marginTop: "var(--space-4)" }}>
            <span aria-hidden="true">ℹ</span>
            <span>
              Positions exit automatically at +8% target, −4% stop, after 10 trading days, or if the trend
              reverses — whichever happens first.
            </span>
          </div>
        </>
      )}
    </div>
  );
}
