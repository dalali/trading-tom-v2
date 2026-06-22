import React from "react";

export default function StatCard({ label, value, valueClassName = "" }) {
  return (
    <div className="stat-card">
      <div className="stat-card-label">{label}</div>
      <div className={`stat-card-value ${valueClassName}`}>{value}</div>
    </div>
  );
}
