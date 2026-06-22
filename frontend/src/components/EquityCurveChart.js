import React from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatDate, formatUsd } from "../utils/format";

/** Equity curve line chart — docs/design.md Section 2.4 / 4.13. Single
 * line, primary-600 stroke, light primary-50 area fill, dashed
 * neutral-200 gridlines, hover tooltip with date + portfolio value. */
export default function EquityCurveChart({ points }) {
  if (!points || points.length === 0) {
    return <p className="text-muted">No equity curve data available.</p>;
  }

  const data = points.map((p) => ({ date: p.date, value: Number(p.total_value) }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
        <CartesianGrid stroke="var(--neutral-200)" strokeDasharray="4 4" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(d) => formatDate(d, { includeYear: false })}
          tick={{ fontSize: 12, fill: "var(--neutral-500)" }}
          minTickGap={40}
        />
        <YAxis
          tickFormatter={(v) => formatUsd(v)}
          tick={{ fontSize: 12, fill: "var(--neutral-500)" }}
          width={80}
        />
        <Tooltip
          formatter={(value) => [formatUsd(value), "Portfolio value"]}
          labelFormatter={(label) => formatDate(label)}
        />
        <Area type="monotone" dataKey="value" stroke="var(--primary-600)" strokeWidth={2} fill="var(--primary-50)" fillOpacity={0.6} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
