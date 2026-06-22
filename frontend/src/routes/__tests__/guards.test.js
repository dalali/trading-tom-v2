import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "../../context/AuthContext";
import RequireAuth from "../RequireAuth";
import RequireAdmin from "../RequireAdmin";
import * as endpoints from "../../api/endpoints";
import { api } from "../../api/client";

jest.mock("../../api/endpoints");

function renderAt(path, { refresh, me } = {}) {
  jest.spyOn(api, "refresh").mockImplementation(refresh || (() => Promise.reject(new Error("no cookie"))));
  if (me) {
    endpoints.fetchMe.mockResolvedValue(me);
  }

  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route element={<RequireAuth />}>
            <Route path="/dashboard" element={<div>Dashboard Page</div>} />
            <Route element={<RequireAdmin />}>
              <Route path="/admin/users" element={<div>Admin Users Page</div>} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("RequireAuth", () => {
  afterEach(() => jest.restoreAllMocks());

  test("redirects to /login when there is no valid session", async () => {
    renderAt("/dashboard");
    await waitFor(() => expect(screen.getByText("Login Page")).toBeInTheDocument());
  });

  test("renders the protected route once a session is restored", async () => {
    renderAt("/dashboard", {
      refresh: () => Promise.resolve({ access_token: "tok" }),
      me: { user_id: 1, email: "j@example.com", display_name: "Jane", role: "user", is_active: true },
    });
    await waitFor(() => expect(screen.getByText("Dashboard Page")).toBeInTheDocument());
  });
});

describe("RequireAdmin", () => {
  afterEach(() => jest.restoreAllMocks());

  test("a user-role session hitting /admin/* is redirected to /dashboard, not shown a 403 page", async () => {
    renderAt("/admin/users", {
      refresh: () => Promise.resolve({ access_token: "tok" }),
      me: { user_id: 1, email: "j@example.com", display_name: "Jane", role: "user", is_active: true },
    });
    await waitFor(() => expect(screen.getByText("Dashboard Page")).toBeInTheDocument());
    expect(screen.queryByText("Admin Users Page")).not.toBeInTheDocument();
  });

  test("an admin-role session reaches the admin route", async () => {
    renderAt("/admin/users", {
      refresh: () => Promise.resolve({ access_token: "tok" }),
      me: { user_id: 9, email: "sam@example.com", display_name: "Sam", role: "admin", is_active: true },
    });
    await waitFor(() => expect(screen.getByText("Admin Users Page")).toBeInTheDocument());
  });
});
