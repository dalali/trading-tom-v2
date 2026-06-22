import React from "react";
import { formatUsd, formatUsdPrecise } from "../utils/format";

/** Renders a USD amount with full precision available on hover
 * (docs/design.md Section 6.1 "precision on demand"). */
export default function Money({ value, className = "" }) {
  return (
    <span className={`tabular-nums ${className}`} title={formatUsdPrecise(value)}>
      {formatUsd(value)}
    </span>
  );
}
