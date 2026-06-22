import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import { AuthProvider, useAuth } from "../AuthContext";
import * as endpoints from "../../api/endpoints";
import { api } from "../../api/client";

jest.mock("../../api/endpoints");

function Probe() {
  const { status, isAuthenticated, isAdmin, user, login, logout } = useAuth();
  return (
    <div>
      <div data-testid="status">{status}</div>
      <div data-testid="authenticated">{String(isAuthenticated)}</div>
      <div data-testid="admin">{String(isAdmin)}</div>
      <div data-testid="user">{user ? user.displayName : "none"}</div>
      <button onClick={() => login("jane@example.com", "secret123")}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  let refreshSpy;

  beforeEach(() => {
    jest.clearAllMocks();
    // No session to restore by default — /auth/refresh fails (no cookie).
    refreshSpy = jest.spyOn(api, "refresh").mockRejectedValue(new Error("no cookie"));
  });

  afterEach(() => {
    refreshSpy.mockRestore();
  });

  test("starts in loading state, settles to unauthenticated when refresh fails", async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
  });

  test("restores an authenticated session on load when the refresh cookie is valid", async () => {
    refreshSpy.mockResolvedValue({ access_token: "tok-123" });
    endpoints.fetchMe.mockResolvedValue({
      user_id: 1,
      email: "jane@example.com",
      display_name: "Jane Doe",
      role: "user",
      is_active: true,
    });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("user")).toHaveTextContent("Jane Doe");
    expect(screen.getByTestId("admin")).toHaveTextContent("false");
  });

  test("login() sets authenticated state and role on success", async () => {
    endpoints.login.mockResolvedValue({ access_token: "tok-abc", role: "admin", user_id: 7 });
    endpoints.fetchMe.mockResolvedValue({
      user_id: 7,
      email: "sam@example.com",
      display_name: "Sam Admin",
      role: "admin",
      is_active: true,
    });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));

    await act(async () => {
      screen.getByText("login").click();
    });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("admin")).toHaveTextContent("true");
  });

  test("login() surfaces a 401 as a non-throwing failure result", async () => {
    const { ApiError } = await import("../../api/client");
    endpoints.login.mockRejectedValue(new ApiError("Invalid email or password", 401));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));

    await act(async () => {
      screen.getByText("login").click();
    });

    // Stays unauthenticated — login() itself never throws past the caller.
    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
  });

  test("logout() clears session state", async () => {
    endpoints.login.mockResolvedValue({ access_token: "tok-abc", role: "user", user_id: 3 });
    endpoints.fetchMe.mockResolvedValue({
      user_id: 3,
      email: "j@example.com",
      display_name: "J",
      role: "user",
      is_active: true,
    });
    endpoints.logout.mockResolvedValue(null);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));

    await act(async () => {
      screen.getByText("login").click();
    });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    await act(async () => {
      screen.getByText("logout").click();
    });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"));
  });
});
