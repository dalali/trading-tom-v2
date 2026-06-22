import React, { useState } from "react";
import { Link } from "react-router-dom";
import { fetchTradesToday, fetchTradesTodayCsv } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import TradeTable from "../../components/TradeTable";
import LoadingSkeleton from "../../components/LoadingSkeleton";
import ErrorState from "../../components/ErrorState";
import EmptyState from "../../components/EmptyState";
import { useToast } from "../../context/ToastContext";
import { PATHS } from "../../routes/paths";

/** Admin aggregate trades-today view — docs/design.md Section 4.9. */
export default function TradesTodayPage() {
  const { showToast } = useToast();
  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState("");

  const { data, loading, error, refetch } = useFetch(
    () => fetchTradesToday({ ticker: ticker || undefined, side: side || undefined }),
    [ticker, side]
  );

  async function handleExportCsv() {
    try {
      // Goes through the API client (Bearer token + refresh-retry-once),
      // not a plain window.open()/<a href> navigation, which would not
      // carry the in-memory access token (architecture 6.1).
      const csvText = await fetchTradesTodayCsv({ ticker: ticker || undefined, side: side || undefined });
      const blob = new Blob([csvText], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "trades-today.csv";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      showToast(err.message || "Couldn't export CSV.", "error");
    }
  }

  return (
    <div>
      <div className="card-header" style={{ marginBottom: "var(--space-2)" }}>
        <h1 className="text-h1" style={{ margin: 0 }}>
          Trades Today
        </h1>
        <button type="button" className="btn btn-secondary" onClick={handleExportCsv}>
          Export CSV
        </button>
      </div>

      <div style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
        <div className="form-field" style={{ marginBottom: 0 }}>
          <label className="form-label" htmlFor="ticker-filter">
            Ticker
          </label>
          <input id="ticker-filter" className="form-input" value={ticker} onChange={(e) => setTicker(e.target.value)} />
        </div>
        <div className="form-field" style={{ marginBottom: 0 }}>
          <label className="form-label" htmlFor="side-filter">
            Side
          </label>
          <select id="side-filter" className="form-select" value={side} onChange={(e) => setSide(e.target.value)}>
            <option value="">All</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </div>
      </div>

      {loading && <LoadingSkeleton rows={6} />}
      {!loading && error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && data && data.items.length === 0 && (
        <EmptyState
          title="No trades have been executed today yet."
          action={
            <Link to={PATHS.adminEngine} className="btn btn-secondary" style={{ textDecoration: "none" }}>
              View Engine Status →
            </Link>
          }
        />
      )}

      {!loading && !error && data && data.items.length > 0 && (
        <>
          <TradeTable trades={data.items} showUser loading={false} error={null} />
          <p className="text-small text-muted" style={{ marginTop: "var(--space-3)" }}>
            {data.summary.trades} trades · {data.summary.users_evaluated} users evaluated ·{" "}
            {data.summary.signals_skipped} signals skipped · {data.summary.errors.length} errors
          </p>
        </>
      )}
    </div>
  );
}
