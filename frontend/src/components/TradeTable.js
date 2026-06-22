import React from "react";
import Money from "./Money";
import PnlText from "./PnlText";
import ReasonBadge from "./ReasonBadge";
import EmptyState from "./EmptyState";
import LoadingSkeleton from "./LoadingSkeleton";
import { formatDate } from "../utils/format";

/** Shared trade-row table — reused by Trade History (4.3), Trades Today
 * (4.9), and Backtest results trade log (4.13), per design's "same table
 * component" reuse intent. `showUser` adds a User column for the
 * cross-user admin feed. */
export default function TradeTable({ trades, loading, error, showUser = false, emptyState }) {
  if (loading) {
    return <LoadingSkeleton rows={6} />;
  }
  if (error) {
    return <EmptyState title="Couldn't load trades" description={error} />;
  }
  if (!trades || trades.length === 0) {
    return emptyState || <EmptyState title="No trades" description="No trades to show." />;
  }

  return (
    <div className="table-wrap dense-responsive">
      <table className="data-table">
        <thead>
          <tr>
            <th>Date</th>
            {showUser && <th>User</th>}
            <th>Side</th>
            <th>Ticker</th>
            <th className="col-num">Qty</th>
            <th className="col-num">Price</th>
            <th className="col-num">Value</th>
            <th className="col-center">Reason</th>
            <th className="col-num">P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id}>
              <td>{formatDate(t.bar_date || t.executed_at)}</td>
              {showUser && <td>{t.user_display_name || t.user_id}</td>}
              <td>{t.side}</td>
              <td className="ticker-cell">{t.ticker}</td>
              <td className="col-num">{t.quantity}</td>
              <td className="col-num">
                <Money value={t.price} />
              </td>
              <td className="col-num">
                <Money value={t.trade_value} />
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

      <div className="mobile-row-cards">
        {trades.map((t) => (
          <div key={t.id} className="mobile-row-card">
            <div className="mobile-row-card-header">
              <span>
                {t.ticker} {t.side}
              </span>
              <span>{formatDate(t.bar_date || t.executed_at, { includeYear: false })}</span>
            </div>
            <div className="mobile-row-card-line">
              <ReasonBadge reason={t.signal_reason} />
            </div>
            <div className="mobile-row-card-line">
              <span>
                Qty {t.quantity} @ <Money value={t.price} />
              </span>
            </div>
            <div className="mobile-row-card-line">
              <PnlText value={t.realized_pnl} naLabel="—" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
