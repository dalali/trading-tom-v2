import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError } from "../api/client";
import { setAccessToken, setUnauthorizedHandler, getAccessToken } from "../api/client";
import { login as loginRequest, logout as logoutRequest, fetchMe } from "../api/endpoints";

// Architecture Section 6.1 — access token in memory only, role/user_id
// alongside it, restored on app load via /auth/refresh (HttpOnly cookie).
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // { userId, email, displayName, role, isActive }
  const [status, setStatus] = useState("loading"); // loading | authenticated | unauthenticated

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(clearSession);
  }, [clearSession]);

  // On first load, try to silently restore a session from the refresh
  // cookie (architecture 6.1 — "restore session on load").
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      try {
        const { api } = await import("../api/client");
        const { access_token } = await api.refresh();
        if (cancelled) return;
        setAccessToken(access_token);
        const me = await fetchMe();
        if (cancelled) return;
        setUser({
          userId: me.user_id,
          email: me.email,
          displayName: me.display_name,
          role: me.role,
          isActive: me.is_active,
        });
        setStatus("authenticated");
      } catch {
        if (!cancelled) {
          clearSession();
        }
      }
    }
    restore();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email, password) => {
    try {
      const data = await loginRequest(email, password);
      setAccessToken(data.access_token);
      const me = await fetchMe();
      setUser({
        userId: me.user_id,
        email: me.email,
        displayName: me.display_name,
        role: me.role,
        isActive: me.is_active,
      });
      setStatus("authenticated");
      return { ok: true };
    } catch (err) {
      if (err instanceof ApiError) {
        return { ok: false, status: err.status, message: err.message };
      }
      return { ok: false, status: 0, message: "Network error. Please try again." };
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } catch {
      // best-effort — clear local state regardless
    }
    clearSession();
  }, [clearSession]);

  const value = useMemo(
    () => ({
      user,
      status,
      isAuthenticated: status === "authenticated",
      isAdmin: user?.role === "admin",
      login,
      logout,
      getAccessToken,
    }),
    [user, status, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
