import React from "react";

/** Centered empty-state message, optionally with a primary action —
 * docs/design.md Section 5.5. Never literally blank. */
export default function EmptyState({ title, description, action }) {
  return (
    <div className="table-empty">
      {title && <div className="text-h3">{title}</div>}
      {description && <div className="text-muted">{description}</div>}
      {action}
    </div>
  );
}
