import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { PATHS } from "./paths";
import FullPageSpinner from "../components/FullPageSpinner";

/** Any authenticated route (user or admin) — docs/design.md Section 3.4.
 * Redirects to /login?next=<path> if no valid session, preserving the
 * originally-requested path. */
export default function RequireAuth() {
  const { status, isAuthenticated } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <FullPageSpinner />;
  }

  if (!isAuthenticated) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`${PATHS.login}?next=${next}`} replace />;
  }

  return <Outlet />;
}
