import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { PATHS } from "./paths";

/** Admin-only route — docs/design.md Section 3.4. A `user`-role token
 * hitting /admin/* is redirected to /dashboard, mirroring the server's
 * 403 (architecture 6.2) — the UI never relies on hiding the nav link
 * alone, this is UX only, the server check is authoritative. */
export default function RequireAdmin() {
  const { isAdmin } = useAuth();

  if (!isAdmin) {
    return <Navigate to={PATHS.dashboard} replace />;
  }

  return <Outlet />;
}
