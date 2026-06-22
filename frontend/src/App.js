import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";
import AppShell from "./components/AppShell";
import RequireAuth from "./routes/RequireAuth";
import RequireAdmin from "./routes/RequireAdmin";
import RoleHomeRedirect from "./routes/RoleHomeRedirect";
import { PATHS } from "./routes/paths";

import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Dashboard from "./pages/user/Dashboard";
import Positions from "./pages/user/Positions";
import TradeHistory from "./pages/user/TradeHistory";

import UserList from "./pages/admin/UserList";
import UserInspector from "./pages/admin/UserInspector";
import TradesTodayPage from "./pages/admin/TradesTodayPage";
import EnginePage from "./pages/admin/EnginePage";
import BacktestList from "./pages/admin/BacktestList";
import BacktestNew from "./pages/admin/BacktestNew";
import BacktestDetail from "./pages/admin/BacktestDetail";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path={PATHS.login} element={<Login />} />

            <Route element={<RequireAuth />}>
              <Route element={<AppShell />}>
                <Route path="/" element={<RoleHomeRedirect />} />

                {/* Regular user (any authenticated role) */}
                <Route path={PATHS.dashboard} element={<Dashboard />} />
                <Route path={PATHS.positions} element={<Positions />} />
                <Route path={PATHS.trades} element={<TradeHistory />} />

                {/* Admin-only */}
                <Route element={<RequireAdmin />}>
                  <Route path={PATHS.admin} element={<Navigate to={PATHS.adminUsers} replace />} />
                  <Route path={PATHS.adminUsers} element={<UserList />} />
                  <Route path={PATHS.adminUserDetail} element={<UserInspector />} />
                  <Route path={PATHS.adminTradesToday} element={<TradesTodayPage />} />
                  <Route path={PATHS.adminEngine} element={<EnginePage />} />
                  <Route path={PATHS.adminBacktests} element={<BacktestList />} />
                  <Route path={PATHS.adminBacktestNew} element={<BacktestNew />} />
                  <Route path={PATHS.adminBacktestDetail} element={<BacktestDetail />} />
                </Route>
              </Route>
            </Route>

            <Route path="*" element={<NotFound />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
