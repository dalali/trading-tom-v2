import React, { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { fetchMyTrades } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import TradeFilters from "../../components/TradeFilters";
import TradeTable from "../../components/TradeTable";
import Pagination from "../../components/Pagination";
import EmptyState from "../../components/EmptyState";

/** Regular user trade history — docs/design.md Section 4.3. Filter state
 * lives in the URL query string (Section 5.2). */
export default function TradeHistory() {
  const [params, setParams] = useSearchParams();
  const ticker = params.get("ticker") || undefined;
  const from = params.get("from") || undefined;
  const to = params.get("to") || undefined;
  const page = Number(params.get("page") || 1);
  const [pageSize, setPageSize] = useState(25);

  const [draft, setDraft] = useState({ ticker, from, to });

  const { data, loading, error, refetch } = useFetch(
    () => fetchMyTrades({ ticker, from, to, page, page_size: pageSize }),
    [ticker, from, to, page, pageSize]
  );

  const tickerOptions = useMemo(() => {
    const set = new Set((data?.items || []).map((t) => t.ticker));
    if (ticker) set.add(ticker);
    return Array.from(set).sort();
  }, [data, ticker]);

  function applyFilters() {
    const next = new URLSearchParams();
    if (draft.ticker) next.set("ticker", draft.ticker);
    if (draft.from) next.set("from", draft.from);
    if (draft.to) next.set("to", draft.to);
    next.set("page", "1");
    setParams(next);
  }

  function clearFilters() {
    setDraft({ ticker: undefined, from: undefined, to: undefined });
    setParams(new URLSearchParams());
  }

  function goToPage(nextPage) {
    const next = new URLSearchParams(params);
    next.set("page", String(nextPage));
    setParams(next);
  }

  const hasActiveFilters = Boolean(ticker || from || to);

  return (
    <div>
      <h1 className="text-h1 page-title">Trade History</h1>

      <TradeFilters
        tickerOptions={tickerOptions}
        ticker={draft.ticker}
        from={draft.from}
        to={draft.to}
        onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
        onApply={applyFilters}
        onClear={clearFilters}
        hasActiveFilters={hasActiveFilters}
      />

      <TradeTable
        trades={data?.items}
        loading={loading}
        error={error}
        emptyState={
          hasActiveFilters ? (
            <EmptyState
              title="No trades match these filters."
              action={
                <button type="button" className="btn btn-secondary" onClick={clearFilters}>
                  Clear filters
                </button>
              }
            />
          ) : (
            <EmptyState
              title="No trades yet."
              description="The engine evaluates your account on the next scheduled run — check back after market close."
            />
          )
        }
      />

      {!loading && !error && data && data.total > 0 && (
        <Pagination
          page={page}
          pageSize={pageSize}
          total={data.total}
          onPageChange={goToPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            goToPage(1);
          }}
        />
      )}

      {error && (
        <button type="button" className="btn btn-secondary" onClick={refetch}>
          Retry
        </button>
      )}
    </div>
  );
}
