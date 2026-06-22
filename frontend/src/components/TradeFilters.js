import React from "react";

/** Shared ticker + date-range filter bar — docs/design.md Section 4.3 /
 * 5.2. Filter state lives in the URL (callers own the query string). */
export default function TradeFilters({
  tickerOptions,
  ticker,
  from,
  to,
  onChange,
  onApply,
  onClear,
  hasActiveFilters,
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onApply();
      }}
      style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)", alignItems: "flex-end", marginBottom: "var(--space-4)" }}
    >
      <div className="form-field" style={{ marginBottom: 0 }}>
        <label className="form-label" htmlFor="ticker-filter">
          Ticker
        </label>
        <select
          id="ticker-filter"
          className="form-select"
          value={ticker || ""}
          onChange={(e) => onChange({ ticker: e.target.value || undefined })}
        >
          <option value="">All</option>
          {(tickerOptions || []).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
      <div className="form-field" style={{ marginBottom: 0 }}>
        <label className="form-label" htmlFor="from-filter">
          From
        </label>
        <input
          id="from-filter"
          type="date"
          className="form-input"
          value={from || ""}
          onChange={(e) => onChange({ from: e.target.value || undefined })}
        />
      </div>
      <div className="form-field" style={{ marginBottom: 0 }}>
        <label className="form-label" htmlFor="to-filter">
          To
        </label>
        <input
          id="to-filter"
          type="date"
          className="form-input"
          value={to || ""}
          onChange={(e) => onChange({ to: e.target.value || undefined })}
        />
      </div>
      <button type="submit" className="btn btn-primary">
        Apply
      </button>
      {hasActiveFilters && (
        <button type="button" className="btn btn-secondary" onClick={onClear}>
          Clear
        </button>
      )}
    </form>
  );
}
