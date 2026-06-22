// Route path constants — docs/design.md Section 3.1 sitemap.
export const PATHS = {
  login: "/login",
  dashboard: "/dashboard",
  positions: "/positions",
  trades: "/trades",
  admin: "/admin",
  adminUsers: "/admin/users",
  adminUserDetail: "/admin/users/:userId",
  adminTradesToday: "/admin/trades-today",
  adminEngine: "/admin/engine",
  adminBacktests: "/admin/backtests",
  adminBacktestNew: "/admin/backtests/new",
  adminBacktestDetail: "/admin/backtests/:backtestId",
};

export function adminUserDetailPath(userId) {
  return `/admin/users/${userId}`;
}

export function adminBacktestDetailPath(backtestId) {
  return `/admin/backtests/${backtestId}`;
}
