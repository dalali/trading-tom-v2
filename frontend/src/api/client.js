// Fetch wrapper — architecture Section 6.1 JWT flow.
//
// Access token lives only in memory (module-level + AuthContext mirror),
// never localStorage (XSS hardening). The refresh token is an HttpOnly
// cookie the browser sends automatically; this client never reads or
// writes it directly.
//
// API base: defaults to "" (relative paths), which works through CRA's
// dev-server `proxy` field (package.json) in local Docker Compose, so
// the browser only ever talks to one origin and the refresh cookie
// stays first-party (architecture 8.1's CRA-proxy option). Can be
// overridden with REACT_APP_API_BASE for non-proxied deployments.
const API_BASE = process.env.REACT_APP_API_BASE || "";

let accessToken = null;
let onUnauthorized = null;

export function setAccessToken(token) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

// Registered by AuthContext so the client can clear app state when a
// refresh ultimately fails (e.g. redirect to /login).
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

let refreshPromise = null;

async function doRefresh() {
  if (refreshPromise) {
    return refreshPromise;
  }
  refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  })
    .then(async (res) => {
      if (!res.ok) {
        throw new ApiError("Session expired", res.status);
      }
      const data = await res.json();
      setAccessToken(data.access_token);
      return data.access_token;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

/**
 * @param {string} path - e.g. "/me/account"
 * @param {object} options - { method, body, query, isRetry, raw }
 */
async function request(path, options = {}) {
  const { method = "GET", body, query, _isRetry = false, raw = false } = options;

  let url = `${API_BASE}${path}`;
  if (query) {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        params.set(key, value);
      }
    });
    const qs = params.toString();
    if (qs) {
      url += `?${qs}`;
    }
  }

  const headers = { "Content-Type": "application/json" };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && !_isRetry && path !== "/auth/refresh") {
    try {
      await doRefresh();
      return request(path, { ...options, _isRetry: true });
    } catch {
      setAccessToken(null);
      if (onUnauthorized) {
        onUnauthorized();
      }
      throw new ApiError("Not authenticated", 401);
    }
  }

  if (res.status === 204) {
    return null;
  }

  const text = await res.text();

  if (raw) {
    if (!res.ok) {
      throw new ApiError(res.statusText || "Request failed", res.status);
    }
    return text;
  }

  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!res.ok) {
    const message = (payload && payload.detail) || res.statusText || "Request failed";
    throw new ApiError(message, res.status, payload && payload.detail);
  }

  return payload;
}

export const api = {
  get: (path, query) => request(path, { method: "GET", query }),
  post: (path, body, query) => request(path, { method: "POST", body, query }),
  delete: (path, query) => request(path, { method: "DELETE", query }),
  // Returns the raw response body as text (e.g. CSV exports), still going
  // through the same Bearer-token + refresh-on-401-retry-once flow as
  // every other authenticated request — a plain window.open()/<a href>
  // would bypass the in-memory access token entirely (architecture 6.1).
  getText: (path, query) => request(path, { method: "GET", query, raw: true }),
  refresh: doRefresh,
};
