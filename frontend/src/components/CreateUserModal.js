import React, { useState } from "react";
import Modal from "./Modal";
import { createUser } from "../api/endpoints";
import { useToast } from "../context/ToastContext";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MIN_PASSWORD_LENGTH = 8;

/** Create-user modal — docs/design.md Section 4.6. */
export default function CreateUserModal({ onClose, onCreated }) {
  const { showToast } = useToast();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [touched, setTouched] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState(null);

  const errors = {
    displayName: displayName.trim() === "" ? "Display name is required." : null,
    email: !EMAIL_RE.test(email) ? "Enter a valid email address." : null,
    password:
      password.length < MIN_PASSWORD_LENGTH
        ? `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`
        : null,
  };
  const hasErrors = Object.values(errors).some(Boolean);

  async function handleSubmit(e) {
    e.preventDefault();
    setTouched({ displayName: true, email: true, password: true });
    if (hasErrors) return;

    setSubmitting(true);
    setServerError(null);
    try {
      await createUser({ display_name: displayName, email, password, role });
      showToast(`${displayName} created.`, "success");
      onCreated();
    } catch (err) {
      if (err.status === 409) {
        setServerError("A user with this email already exists.");
      } else {
        setServerError(err.message || "Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title="Create User"
      onClose={onClose}
      busy={submitting}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" form="create-user-form" className="btn btn-primary" disabled={submitting || hasErrors}>
            {submitting ? "Creating…" : "Create User"}
          </button>
        </>
      }
    >
      <form id="create-user-form" onSubmit={handleSubmit}>
        {serverError && (
          <div className="banner banner-danger" role="alert">
            <span aria-hidden="true">!</span>
            <span>{serverError}</span>
          </div>
        )}

        <div className="form-field">
          <label className="form-label" htmlFor="display-name">
            Display name
          </label>
          <input
            id="display-name"
            className={`form-input ${touched.displayName && errors.displayName ? "has-error" : ""}`}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, displayName: true }))}
          />
          {touched.displayName && errors.displayName && <div className="form-error">{errors.displayName}</div>}
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="create-email">
            Email
          </label>
          <input
            id="create-email"
            type="email"
            className={`form-input ${(touched.email && errors.email) || serverError ? "has-error" : ""}`}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, email: true }))}
          />
          {touched.email && errors.email && <div className="form-error">{errors.email}</div>}
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="create-password">
            Initial password
          </label>
          <input
            id="create-password"
            type="password"
            className={`form-input ${touched.password && errors.password ? "has-error" : ""}`}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, password: true }))}
          />
          {touched.password && errors.password ? (
            <div className="form-error">{errors.password}</div>
          ) : (
            <div className="form-help">Share this with the user out-of-band — there is no invite email sent automatically.</div>
          )}
        </div>

        <div className="form-field">
          <span className="form-label">Role</span>
          <div style={{ display: "flex", gap: "var(--space-4)" }}>
            <label>
              <input type="radio" name="role" value="admin" checked={role === "admin"} onChange={() => setRole("admin")} /> Admin
            </label>
            <label>
              <input type="radio" name="role" value="user" checked={role === "user"} onChange={() => setRole("user")} /> Regular
              User
            </label>
          </div>
        </div>
      </form>
    </Modal>
  );
}
