import React from "react";
import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div style={{ textAlign: "center", padding: "64px 16px" }}>
      <h1 className="text-h1">Page not found</h1>
      <p className="text-muted">The page you're looking for doesn't exist.</p>
      <Link to="/" className="btn btn-primary" style={{ textDecoration: "none" }}>
        Go home
      </Link>
    </div>
  );
}
