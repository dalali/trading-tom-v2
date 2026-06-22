import React, { useState } from "react";
import Modal from "./Modal";
import Money from "./Money";
import { fundUser } from "../api/endpoints";
import { useToast } from "../context/ToastContext";
import { formatUsd } from "../utils/format";

const PRESETS = [1000, 10000, 100000];

/** Fund account modal — docs/design.md Section 4.7. */
export default function FundAccountModal({ user, currentBalance, onClose, onFunded }) {
  const { showToast } = useToast();
  const [amount, setAmount] = useState("");
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState(null);

  const numericAmount = Number(amount);
  const isValid = amount !== "" && !Number.isNaN(numericAmount) && numericAmount > 0;
  const newBalance = isValid ? Number(currentBalance) + numericAmount : Number(currentBalance);
  const isFirstFunding = Number(currentBalance) === 0;

  async function handleSubmit(e) {
    e.preventDefault();
    setTouched(true);
    if (!isValid) return;

    setSubmitting(true);
    setServerError(null);
    try {
      const result = await fundUser(user.id, String(numericAmount));
      showToast(`${formatUsd(numericAmount)} added to ${user.display_name}. New balance: ${formatUsd(result.new_balance)}.`, "success");
      onFunded(result.new_balance);
    } catch (err) {
      setServerError(err.message || "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title={`Fund Account: ${user.display_name}`}
      onClose={onClose}
      busy={submitting}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" form="fund-account-form" className="btn btn-primary" disabled={submitting || !isValid}>
            {submitting ? "Funding…" : "Fund Account"}
          </button>
        </>
      }
    >
      <form id="fund-account-form" onSubmit={handleSubmit}>
        {serverError && (
          <div className="banner banner-danger" role="alert">
            <span aria-hidden="true">!</span>
            <span>{serverError}</span>
          </div>
        )}

        <p>
          Current balance: <Money value={currentBalance} />
        </p>

        <div className="form-field">
          <label className="form-label" htmlFor="fund-amount">
            Amount to add
          </label>
          <div className="currency-input-wrap">
            <span className="currency-prefix">$</span>
            <input
              id="fund-amount"
              type="number"
              step="0.01"
              min="0"
              className={`form-input ${touched && !isValid ? "has-error" : ""}`}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              onBlur={() => setTouched(true)}
            />
          </div>
          {touched && !isValid && <div className="form-error">Amount must be greater than $0.</div>}
        </div>

        <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
          {PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setAmount(String(preset));
                setTouched(true);
              }}
            >
              {formatUsd(preset)}
            </button>
          ))}
        </div>

        <p>
          New balance will be: <strong>{formatUsd(newBalance)}</strong>
        </p>

        {isFirstFunding && isValid && (
          <div className="banner banner-info">
            <span aria-hidden="true">ℹ</span>
            <span>This will activate {user.display_name} for trading starting with the next scheduled engine run.</span>
          </div>
        )}

        <p className="text-small text-muted">This is an additive top-up only — there is no withdraw/set-balance action in this version.</p>
      </form>
    </Modal>
  );
}
