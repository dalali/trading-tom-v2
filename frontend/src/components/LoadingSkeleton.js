import React from "react";

/** Skeleton placeholder rows — docs/design.md Section 2.4 / 5.5. Never a
 * full-page spinner once the shell has rendered. */
export default function LoadingSkeleton({ rows = 4 }) {
  return (
    <div role="status" aria-live="polite" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-row" />
      ))}
    </div>
  );
}
