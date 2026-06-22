import React, { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { PATHS } from "../routes/paths";

const USER_NAV = [
  { to: PATHS.dashboard, label: "Dashboard" },
  { to: PATHS.positions, label: "Positions" },
  { to: PATHS.trades, label: "Trade History" },
];

const ADMIN_NAV = [
  { to: PATHS.adminUsers, label: "Users" },
  { to: PATHS.adminTradesToday, label: "Trades Today" },
  { to: PATHS.adminEngine, label: "Engine" },
  { to: PATHS.adminBacktests, label: "Backtests" },
];

/** Shared shell — docs/design.md Section 2.4 (nav shell) / 3.2 (admin vs
 * user nav) / 7.2 (mobile collapse) / 8.3 (skip link). */
export default function AppShell() {
  const { user, isAdmin, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navItems = isAdmin ? ADMIN_NAV : USER_NAV;

  async function handleLogout() {
    await logout();
  }

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>

      <div className="app-topbar">
        <button
          type="button"
          className="hamburger-btn"
          aria-label="Open navigation menu"
          onClick={() => setSidebarOpen(true)}
        >
          ☰
        </button>
        <strong>◆ trading-tom</strong>
      </div>

      {sidebarOpen && (
        <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />
      )}

      <nav
        className={`app-sidebar ${isAdmin ? "role-admin" : "role-user"} ${sidebarOpen ? "open" : ""}`}
        aria-label="Main navigation"
      >
        <div className="sidebar-brand">
          ◆ trading-tom
          {isAdmin && <span className="sidebar-admin-tag">ADMIN</span>}
        </div>
        <div className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
        <div className="sidebar-footer">
          <div className="sidebar-user-name">{user?.displayName}</div>
          <div className="sidebar-user-role">{isAdmin ? "Admin" : "Regular User"}</div>
          <button type="button" className="logout-btn" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </nav>

      <main className="app-main">
        <div className="app-content" id="main-content" tabIndex={-1}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
