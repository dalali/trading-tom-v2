// Data display conventions — docs/design.md Section 6.

/** Format a decimal-string/number as "$X,XXX.XX" (Section 6.1). Negative
 * values render as "-$X,XXX.XX" (leading minus before the $ sign). */
export function formatUsd(value) {
  const num = Number(value);
  if (Number.isNaN(num)) return "$0.00";
  const abs = Math.abs(num);
  const formatted = abs.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return num < 0 ? `-$${formatted}` : `$${formatted}`;
}

/** Full, unrounded precision string for a title-attribute tooltip
 * (Section 6.1 "precision on demand"). */
export function formatUsdPrecise(value) {
  const num = Number(value);
  if (Number.isNaN(num)) return "$0.0000";
  const abs = Math.abs(num);
  const formatted = abs.toLocaleString("en-US", {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  });
  return num < 0 ? `-$${formatted}` : `$${formatted}`;
}

/** Percentages to 1 decimal place (e.g. "+3.9%", "-11.4%"), except win
 * rate which the caller should format as a whole percent separately. */
export function formatPct(value, { signed = true } = {}) {
  const num = Number(value);
  if (Number.isNaN(num)) return "0.0%";
  const sign = signed && num > 0 ? "+" : "";
  return `${sign}${num.toFixed(1)}%`;
}

export function formatWholePct(value) {
  const num = Number(value);
  if (Number.isNaN(num)) return "0%";
  return `${Math.round(num)}%`;
}

/** Dates as "Jun 22, 2026" (Section 6.4) — never numeric MM/DD/YYYY. */
export function formatDate(value, { includeYear = true } = {}) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: includeYear ? "numeric" : undefined,
  });
}

export function formatDateTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  const datePart = d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const timePart = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return `${datePart} · ${timePart}`;
}

/** Three-part P&L convention (Section 6.2): glyph + explicit sign + color.
 * Returns { glyph, text, className } for the caller to render — color is
 * never the only signal. */
export function pnlParts(value, { pct = false } = {}) {
  const num = Number(value);
  if (Number.isNaN(num) || num === 0) {
    return { glyph: "—", text: pct ? "0.0%" : "$0.00", className: "pnl-flat" };
  }
  const isGain = num > 0;
  const glyph = isGain ? "▲" : "▼";
  const text = pct ? formatPct(num) : `${isGain ? "+" : "-"}${formatUsd(Math.abs(num))}`;
  return { glyph, text, className: isGain ? "pnl-gain" : "pnl-loss" };
}

// Reason badge lookup — docs/design.md Section 6.3. Raw enum values are
// never shown verbatim.
export const REASON_BADGES = {
  ENTRY_TREND_MOMENTUM: {
    label: "Trend Entry",
    variant: "neutral",
    tooltip: "Entered on an upward trend-momentum signal.",
  },
  EXIT_PROFIT_TARGET: {
    label: "Profit Target",
    variant: "gain",
    tooltip: "Price rose 8% or more above the entry price.",
  },
  EXIT_STOP_LOSS: {
    label: "Stop Loss",
    variant: "loss",
    tooltip: "Price fell 4% or more below the entry price.",
  },
  EXIT_MAX_HOLD: {
    label: "Max Hold Reached",
    variant: "neutral",
    tooltip: "Held for the maximum 10 trading days.",
  },
  EXIT_TREND_INVALIDATION: {
    label: "Trend Reversed",
    variant: "neutral",
    tooltip: "The underlying trend signal reversed before another exit rule triggered.",
  },
};

export function reasonBadge(reason) {
  return (
    REASON_BADGES[reason] || {
      label: reason || "Unknown",
      variant: "neutral",
      tooltip: "",
    }
  );
}

export function statusBadgeVariant(statusValue) {
  switch (statusValue) {
    case "running":
    case "queued":
      return "info";
    case "complete":
    case "active":
      return "success";
    case "failed":
      return "danger";
    case "deactivated":
    case "inactive":
      return "muted";
    default:
      return "neutral";
  }
}
