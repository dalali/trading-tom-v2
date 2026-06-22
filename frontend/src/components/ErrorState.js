import React from "react";

/** Error (request failed) state — docs/design.md Section 5.5. Plain
 * language, optional retry, never a raw error code/stack trace. */
export default function ErrorState({ message, onRetry }) {
  return (
    <div className="table-empty" role="alert">
      <div aria-hidden="true">⚠</div>
      <div>{message || "Something went wrong. Please try again."}</div>
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
