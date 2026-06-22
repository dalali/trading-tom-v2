import React from "react";

export default function Badge({ children, variant = "neutral", title }) {
  return (
    <span className={`badge badge-${variant}`} title={title}>
      {children}
    </span>
  );
}
