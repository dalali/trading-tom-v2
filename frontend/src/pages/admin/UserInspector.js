import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchUserDetail, fetchUserTrades } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import LoadingSkeleton from "../../components/LoadingSkeleton";
import ErrorState from "../../components/ErrorState";
import StatCard from "../../components/StatCard";
import Money from "../../components/Money";
import PnlText from "../../components/PnlText";
import Badge from "../../components/Badge";
import TradeTable from "../../components/TradeTable";
import Pagination from "../../components/Pagination";
import FundAccountModal from "../../components/FundAccountModal";
import { formatDate } from "../../utils/format";

/** Admin per-user inspector — docs/design.md Section 4.8. Reuses the
 * same stat-card / table components as the Regular User dashboard
 * (Section 4.2-4.4), re-skinned with the admin shell, per the design
 * doc's explicit reuse intent. */
export default function UserInspector() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState("positions");
  const [fundOpen, setFundOpen] = useState(false);
  const [page, setPage] = useState(1);

  const { data, loading, error, refetch } = useFetch(() => fetchUserDetail(userId), [userId]);

  const trades = useFetch(
    () => (tab === "trades" ? fetchUserTrades(userId, { page, page_size: 25 }) : Promise.resolve(null)),
    [userId, tab, page]
  );

  if (loading) return <LoadingSkeleton rows={6} />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (!data) return null;

  const { user, account, positions } = data;
  const totalValue = Number(account.cash_balance) + Number(account.equity_value);

  return (
    <div>
      <p className="page-subtitle">
        <a href="/admin/users" onClick={(e) => { e.preventDefault(); navigate("/admin/users"); }}>
          Users
        </a>{" "}
        / {user.display_name}
      </p>

      <div className="card-header" style={{ marginBottom: "var(--space-4)" }}>
        <div>
          <strong>{user.display_name}</strong> · {user.email} ·{" "}
          {user.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="muted">Deactivated</Badge>}
        </div>
        {user.is_active && (
          <button type="button" className="btn btn-primary" onClick={() => setFundOpen(true)}>
            Fund Account
          </button>
        )}
      </div>

      {!user.is_active && (
        <div className="banner banner-warning">
          <span aria-hidden="true">⊘</span>
          <span>This account is deactivated and cannot log in. Historical data below is preserved and viewable.</span>
        </div>
      )}

      <div className="stat-grid" style={{ marginBottom: "var(--space-4)" }}>
        <StatCard label="Total Value" value={<Money value={totalValue} />} />
        <StatCard label="Cash Balance" value={<Money value={account.cash_balance} />} />
        <StatCard label="Equity Value" value={<Money value={account.equity_value} />} />
      </div>

      <div className="stat-grid-2" style={{ marginBottom: "var(--space-5)" }}>
        <div className="stat-card">
          <div className="stat-card-label">Realized P&amp;L (lifetime)</div>
          <PnlText value={account.realized_pnl} />
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Unrealized P&amp;L (open)</div>
          <PnlText value={null} naLabel="Not available" />
        </div>
      </div>

      <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
        <button
          type="button"
          className={tab === "positions" ? "btn btn-primary" : "btn btn-secondary"}
          onClick={() => setTab("positions")}
        >
          Positions ({positions.length})
        </button>
        <button
          type="button"
          className={tab === "trades" ? "btn btn-primary" : "btn btn-secondary"}
          onClick={() => setTab("trades")}
        >
          Trade History
        </button>
      </div>

      {tab === "positions" && (
        positions.length === 0 ? (
          <p className="text-muted">No open positions.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th className="col-num">Qty</th>
                  <th className="col-num">Entry Price</th>
                  <th>Entry Date</th>
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {tab === "trades" && (
        <>
          <TradeTable trades={trades.data?.items} loading={trades.loading} error={trades.error} />
          {trades.data && trades.data.total > 0 && (
            <Pagination page={page} pageSize={25} total={trades.data.total} onPageChange={setPage} />
          )}
        </>
      )}

      {fundOpen && (
        <FundAccountModal
          user={user}
          currentBalance={totalValue}
          onClose={() => setFundOpen(false)}
          onFunded={() => {
            setFundOpen(false);
            refetch();
          }}
        />
      )}
    </div>
  );
}
