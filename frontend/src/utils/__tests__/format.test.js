import { formatUsd, formatPct, pnlParts, reasonBadge } from "../format";

describe("formatUsd", () => {
  test("formats positive values with thousands separator and 2dp", () => {
    expect(formatUsd(108420.55)).toBe("$108,420.55");
  });

  test("formats negative values with leading minus before the $ sign", () => {
    expect(formatUsd(-84)).toBe("-$84.00");
  });

  test("formats zero as $0.00", () => {
    expect(formatUsd(0)).toBe("$0.00");
  });

  test("falls back to $0.00 for non-numeric input", () => {
    expect(formatUsd("not-a-number")).toBe("$0.00");
  });
});

describe("formatPct", () => {
  test("adds an explicit + sign for positive values", () => {
    expect(formatPct(3.9)).toBe("+3.9%");
  });

  test("keeps the - sign for negative values without doubling it", () => {
    expect(formatPct(-11.4)).toBe("-11.4%");
  });
});

describe("pnlParts", () => {
  test("gain: up glyph, explicit +, gain color class", () => {
    const result = pnlParts(292);
    expect(result.glyph).toBe("▲");
    expect(result.text).toBe("+$292.00");
    expect(result.className).toBe("pnl-gain");
  });

  test("loss: down glyph, explicit -, loss color class", () => {
    const result = pnlParts(-127.8);
    expect(result.glyph).toBe("▼");
    expect(result.text).toBe("-$127.80");
    expect(result.className).toBe("pnl-loss");
  });

  test("zero/flat: em-dash glyph, no sign, neutral class (Section 6.2 — flat is its own state)", () => {
    const result = pnlParts(0);
    expect(result.glyph).toBe("—");
    expect(result.text).toBe("$0.00");
    expect(result.className).toBe("pnl-flat");
  });
});

describe("reasonBadge", () => {
  test("never renders a raw enum value — always maps to a human label", () => {
    expect(reasonBadge("EXIT_STOP_LOSS").label).toBe("Stop Loss");
    expect(reasonBadge("EXIT_STOP_LOSS").variant).toBe("loss");
  });

  test("profit target is gain-tinted, max-hold stays neutral (outcome-agnostic)", () => {
    expect(reasonBadge("EXIT_PROFIT_TARGET").variant).toBe("gain");
    expect(reasonBadge("EXIT_MAX_HOLD").variant).toBe("neutral");
  });

  test("unknown reasons fall back gracefully instead of throwing", () => {
    expect(reasonBadge("SOMETHING_NEW").label).toBe("SOMETHING_NEW");
  });
});
