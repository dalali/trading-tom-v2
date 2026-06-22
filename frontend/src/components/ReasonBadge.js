import React from "react";
import Badge from "./Badge";
import { reasonBadge } from "../utils/format";

export default function ReasonBadge({ reason }) {
  const { label, variant, tooltip } = reasonBadge(reason);
  return (
    <Badge variant={variant} title={tooltip}>
      {label}
    </Badge>
  );
}
