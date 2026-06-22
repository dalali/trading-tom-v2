import React from "react";
import { pnlParts, formatUsdPrecise } from "../utils/format";

/** Three-part P&L convention — docs/design.md Section 6.2. */
export default function PnlText({ value, pct = false, naLabel }) {
  if (value === null || value === undefined) {
    return <span className="pnl pnl-flat">{naLabel || "—"}</span>;
  }
  const { glyph, text, className } = pnlParts(value, { pct });
  const title = pct ? undefined : formatUsdPrecise(value);
  return (
    <span className={`pnl ${className}`} title={title}>
      <span aria-hidden="true">{glyph}</span>
      <span>{text}</span>
    </span>
  );
}
