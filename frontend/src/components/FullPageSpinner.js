import React from "react";

/** Full-page spinner — acceptable only for the very first app load before
 * any shell has rendered (docs/design.md Section 5.5). */
export default function FullPageSpinner() {
  return (
    <div
      style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}
      role="status"
      aria-label="Loading application"
    >
      <span className="text-muted">Loading…</span>
    </div>
  );
}
