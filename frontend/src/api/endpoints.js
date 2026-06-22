// Typed-ish wrappers around the exact API contract — architecture
// Section 5 (route list). Keeping all paths/params in one place avoids
// stringly-typed URLs scattered through page components.
import { api } from "./client";

// 5.1 Auth
export const login = (email, password) => api.post("/auth/login", { email, password });
export const logout = () => api.post("/auth/logout");
export const fetchMe = () => api.get("/auth/me");

// 5.3 / 5.4 Self-service portfolio
export const fetchMyAccount = () => api.get("/me/account");
export const fetchMyPositions = () => api.get("/me/positions");
export const fetchMyTrades = ({ ticker, from, to, page, page_size } = {}) =>
  api.get("/me/trades", { ticker, from, to, page, page_size });

// 5.2 Admin — user management
export const fetchUsers = ({ status, q, page, page_size } = {}) =>
  api.get("/admin/users", { status, q, page, page_size });
export const createUser = (body) => api.post("/admin/users", body);
export const fetchUserDetail = (userId) => api.get(`/admin/users/${userId}`);
export const deactivateUser = (userId) => api.delete(`/admin/users/${userId}`);
export const fundUser = (userId, amount) => api.post(`/admin/users/${userId}/fund`, { amount });
export const fetchUserTrades = (userId, { ticker, from, to, page, page_size } = {}) =>
  api.get(`/admin/users/${userId}/trades`, { ticker, from, to, page, page_size });

// 5.4 Admin — trades today
export const fetchTradesToday = ({ ticker, side, user_id } = {}) =>
  api.get("/admin/trades-today", { ticker, side, user_id });
export const fetchTradesTodayCsv = ({ ticker, side, user_id } = {}) =>
  api.getText("/admin/trades-today", { ticker, side, user_id, format: "csv" });

// 5.5 Engine
export const fetchEngineStatus = () => api.get("/admin/engine/status");
export const triggerEngineRun = () => api.post("/admin/engine/run");
export const fetchEngineRuns = ({ page, page_size } = {}) =>
  api.get("/admin/engine/runs", { page, page_size });
export const fetchEngineRunDetail = (runId) => api.get(`/admin/engine/runs/${runId}`);

// 5.6 Backtests
export const createBacktest = (body) => api.post("/admin/backtests", body);
export const fetchBacktests = ({ page, page_size } = {}) =>
  api.get("/admin/backtests", { page, page_size });
export const fetchBacktestDetail = (backtestId) => api.get(`/admin/backtests/${backtestId}`);

// 5.7 Market data
export const fetchMarketDataRange = () => api.get("/admin/market-data/range");
export const fetchMarketDataUniverse = () => api.get("/admin/market-data/universe");
