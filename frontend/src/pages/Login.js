import React, { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { PATHS } from "../routes/paths";

/** Login screen — docs/design.md Section 4.1. Sole entry point; no
 * signup link, generic invalid-credentials message, distinct
 * deactivated-account message. */
export default function Login() {
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (isAuthenticated) {
    const params = new URLSearchParams(location.search);
    const next = params.get("next");
    return <Navigate to={next || PATHS.dashboard} replace />;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const result = await login(email, password);
    setSubmitting(false);
    if (!result.ok) {
      setPassword("");
      if (result.status === 403) {
        setError({ kind: "deactivated", message: "This account has been disabled. Contact your admin for access." });
      } else if (result.status === 401) {
        setError({ kind: "invalid", message: "Invalid email or password." });
      } else {
        setError({ kind: "network", message: result.message || "Something went wrong. Please try again." });
      }
      return;
    }
    const params = new URLSearchParams(location.search);
    const next = params.get("next");
    navigate(next || PATHS.dashboard, { replace: true });
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--neutral-50)",
      }}
    >
      <div className="card" style={{ width: 400 }}>
        <div style={{ textAlign: "center", marginBottom: "var(--space-4)" }}>
          <div className="text-h2">◆ trading-tom</div>
        </div>
        <h1 className="text-h1" style={{ marginBottom: "var(--space-1)" }}>
          Sign in
        </h1>
        <p className="text-muted" style={{ marginTop: 0, marginBottom: "var(--space-4)" }}>
          Paper-trading platform
        </p>

        {error && (
          <div
            className={error.kind === "deactivated" ? "banner banner-warning" : "banner banner-danger"}
            role="alert"
          >
            <span aria-hidden="true">{error.kind === "deactivated" ? "⊘" : "⚠"}</span>
            <span>{error.message}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-field">
            <label className="form-label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              className={`form-input ${error ? "has-error" : ""}`}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className={`form-input ${error ? "has-error" : ""}`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: "100%" }} disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-small text-muted" style={{ textAlign: "center", marginTop: "var(--space-4)" }}>
          Forgot your password? Contact your admin.
        </p>
      </div>
    </div>
  );
}
