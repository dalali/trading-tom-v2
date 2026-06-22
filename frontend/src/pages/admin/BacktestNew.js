import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createBacktest, fetchMarketDataRange, fetchMarketDataUniverse } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import Modal from "../../components/Modal";
import { useToast } from "../../context/ToastContext";
import { PATHS } from "../../routes/paths";

const DEFAULT_STARTING_CAPITAL = "100000";

/** Backtest submission form — docs/design.md Section 4.11. Presented as
 * a modal (per the IA note in Section 3.1); /admin/backtests/new backs
 * it for deep-linkability. */
export default function BacktestNew() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { data: range } = useFetch(fetchMarketDataRange, []);
  const { data: universe } = useFetch(fetchMarketDataUniverse, []);

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [useSubset, setUseSubset] = useState(false);
  const [selectedTickers, setSelectedTickers] = useState([]);
  const [startingCapital, setStartingCapital] = useState(DEFAULT_STARTING_CAPITAL);
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState(null);

  const dateError =
    startDate && endDate && new Date(endDate) <= new Date(startDate)
      ? "End date must be after the start date."
      : null;
  const subsetError = useSubset && selectedTickers.length === 0 ? "Select at least one ticker." : null;
  const capitalError = Number(startingCapital) <= 0 ? "Starting capital must be greater than $0." : null;
  const hasErrors = !startDate || !endDate || Boolean(dateError) || Boolean(subsetError) || Boolean(capitalError);

  function toggleTicker(ticker) {
    setSelectedTickers((prev) => (prev.includes(ticker) ? prev.filter((t) => t !== ticker) : [...prev, ticker]));
  }

  function handleClose() {
    navigate(PATHS.adminBacktests);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setTouched(true);
    if (hasErrors) return;

    setSubmitting(true);
    setServerError(null);
    try {
      await createBacktest({
        start_date: startDate,
        end_date: endDate,
        tickers: useSubset ? selectedTickers : undefined,
        starting_capital: startingCapital,
      });
      showToast("Backtest queued.", "success");
      navigate(PATHS.adminBacktests);
    } catch (err) {
      setServerError(err.message || "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title="New Backtest"
      onClose={handleClose}
      busy={submitting}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={handleClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" form="backtest-new-form" className="btn btn-primary" disabled={submitting || (touched && hasErrors)}>
            {submitting ? "Submitting…" : "Run Backtest"}
          </button>
        </>
      }
    >
      <form id="backtest-new-form" onSubmit={handleSubmit}>
        {serverError && (
          <div className="banner banner-danger" role="alert">
            <span aria-hidden="true">!</span>
            <span>{serverError}</span>
          </div>
        )}

        <div className="form-field">
          <span className="form-label">Date range</span>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <input
              type="date"
              className={`form-input ${touched && dateError ? "has-error" : ""}`}
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              aria-label="Start date"
            />
            <input
              type="date"
              className={`form-input ${touched && dateError ? "has-error" : ""}`}
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              aria-label="End date"
            />
          </div>
          {touched && dateError && <div className="form-error">{dateError}</div>}
          {range && (
            <div className="form-help">
              Available data: {range.earliest || "—"} to {range.latest || "today"}
            </div>
          )}
        </div>

        <div className="form-field">
          <span className="form-label">Tickers</span>
          <label style={{ display: "block" }}>
            <input type="radio" checked={!useSubset} onChange={() => setUseSubset(false)} /> Full universe
            {universe ? ` (${universe.length} tickers)` : ""}
          </label>
          <label style={{ display: "block" }}>
            <input type="radio" checked={useSubset} onChange={() => setUseSubset(true)} /> Choose a subset
          </label>
          {useSubset && (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "var(--space-2)",
                marginTop: "var(--space-2)",
                maxHeight: 160,
                overflowY: "auto",
                border: "var(--border)",
                borderRadius: "var(--radius)",
                padding: "var(--space-2)",
              }}
            >
              {(universe || []).map((ticker) => (
                <label key={ticker} style={{ display: "flex", alignItems: "center", gap: "var(--space-1)" }}>
                  <input type="checkbox" checked={selectedTickers.includes(ticker)} onChange={() => toggleTicker(ticker)} />
                  {ticker}
                </label>
              ))}
            </div>
          )}
          {touched && subsetError && <div className="form-error">{subsetError}</div>}
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="starting-capital">
            Starting capital
          </label>
          <div className="currency-input-wrap">
            <span className="currency-prefix">$</span>
            <input
              id="starting-capital"
              type="number"
              step="0.01"
              min="0"
              className={`form-input ${touched && capitalError ? "has-error" : ""}`}
              value={startingCapital}
              onChange={(e) => setStartingCapital(e.target.value)}
            />
          </div>
          {touched && capitalError && <div className="form-error">{capitalError}</div>}
        </div>
      </form>
    </Modal>
  );
}
