import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { PATHS } from "./paths";

/** "/" redirects to /dashboard (user) or /admin/users (admin) based on
 * role — docs/design.md Section 3.1. Rendered inside RequireAuth, so a
 * valid session is guaranteed here. */
export default function RoleHomeRedirect() {
  const { isAdmin } = useAuth();
  return <Navigate to={isAdmin ? PATHS.adminUsers : PATHS.dashboard} replace />;
}
