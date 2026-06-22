# Architecture: trading-tom-v2

**Status:** Draft for MVP build
**Owner:** Systems Architect (acting against locked PRD at `docs/PRD.md` and design at `docs/design.md`)
**Last updated:** 2026-06-22

This document defines the system architecture, tech stack, data model, trading-engine design, API contracts, auth model, data flows, deployment, and security posture for trading-tom-v2. It builds on the existing repo scaffold (`api/` FastAPI service on port 8000, `frontend/` React service on port 3000, `docker-compose.yml`, `.env.example`) and treats those scaffold commitments as fixed.

It is intentionally pragmatic and MVP-scoped. Decisions made where the PRD/design were silent are flagged inline and consolidated in Section 10 (Assumptions).

---

## Table of Contents

1. [System Overview & Component Diagram](#1-system-overview--component-diagram)
2. [Tech Stack Decisions](#2-tech-stack-decisions)
3. [Data Model](#3-data-model)
4. [Trading Engine Design](#4-trading-engine-design)
5. [API Contracts](#5-api-contracts)
6. [Authentication & Authorization](#6-authentication--authorization)
7. [Data Flow](#7-data-flow)
8. [Deployment Strategy](#8-deployment-strategy)
9. [Security Considerations & Open Risks](#9-security-considerations--open-risks)
10. [Assumptions](#10-assumptions)

---

## 1. System Overview & Component Diagram

### 1.1 What the system is

A single-deployment, local-first paper-trading platform. Four runtime concerns live behind three Docker Compose services:

- **`frontend`** — React SPA (the existing `frontend/` service, port 3000). Pure presentation + client routing; holds no business logic, calls the API.
- **`api`** — FastAPI app (the existing `api/` service, port 8000). Owns all business logic: auth, RBAC, user/account management, portfolio reads, trade-history reads, backtests, market-data access, *and* the scheduled trading engine, which runs **in-process** inside this same container (APScheduler — see Section 2.4). No separate worker container in MVP.
- **`db`** — Postgres (a new service, see Section 8). Single source of truth: users, accounts, positions, trades, fund ledger, engine runs, backtests, and the market-data cache. Named volume for persistence.

The trading engine and the market-data adapter are **modules inside the `api` service**, not separate processes. This is a deliberate MVP simplicity choice (Section 2.4): one Python process, one scheduler, one DB connection pool — no message broker, no Celery/RQ worker, no Redis.

### 1.2 Component diagram (ASCII)

```
                            Browser (desktop-first, responsive)
                                       │
                                       │  HTTPS-in-prod / HTTP-local
                                       │  Authorization: Bearer <JWT>
                                       │  Cookie: refresh_token (HttpOnly)
                                       ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  frontend  (React SPA, CRA dev server, :3000)                               │
│  - React Router (route guards by role)                                      │
│  - TanStack Query (server-state cache, polling for engine status)           │
│  - Axios client (attaches access token, refresh-on-401 interceptor)         │
└───────────────────────────────────────────────────────────────────────────┘
                                       │  REST / JSON  (proxy → :8000)
                                       ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  api  (FastAPI + Uvicorn, :8000)                                            │
│                                                                             │
│   ┌──────────────┐   ┌────────────────┐   ┌──────────────────────────┐      │
│   │ Routers      │   │ Auth / RBAC    │   │ Service layer            │      │
│   │ /auth        │──▶│ JWT issue/     │──▶│ users, accounts,         │      │
│   │ /admin/*     │   │ verify,        │   │ funding, portfolio,      │      │
│   │ /me/*        │   │ role guards,   │   │ trades, backtests        │      │
│   │ /market-data │   │ bootstrap seed │   └────────────┬─────────────┘      │
│   └──────────────┘   └────────────────┘                │                    │
│                                                         │                    │
│   ┌──────────────────────────────┐      ┌──────────────▼─────────────┐      │
│   │ Trading Engine (module)      │      │ Repository / ORM           │      │
│   │ - signal eval (once/run)     │◀────▶│ SQLAlchemy + Alembic       │      │
│   │ - per-user apply (sizing)    │      └──────────────┬─────────────┘      │
│   │ - exit rules                 │                     │                    │
│   │ - backtest = same code path  │      ┌──────────────▼─────────────┐      │
│   └──────────────┬───────────────┘      │ DB session / conn pool     │      │
│                  │                       └──────────────┬─────────────┘      │
│   ┌──────────────▼───────────────┐                      │                   │
│   │ APScheduler (in-process)     │                      │                   │
│   │ - daily cron @ 17:00 ET      │                      │                   │
│   │ - single-run lock (no overlap)                      │                   │
│   └──────────────┬───────────────┘                      │                   │
│                  │                                       │                   │
│   ┌──────────────▼───────────────┐                      │                   │
│   │ Market-Data Adapter (iface)  │                      │                   │
│   │ - yfinance (primary)         │── cache-miss ───────▶│ (writes cache)    │
│   │ - AlphaVantage (fallback)    │◀── cache-hit ────────│ (reads cache)     │
│   └──────────────┬───────────────┘                      │                   │
└──────────────────┼──────────────────────────────────────┼───────────────────┘
                   │ HTTPS (cache miss only)                │
                   ▼                                        ▼
        ┌────────────────────┐               ┌──────────────────────────────┐
        │ Yahoo Finance      │               │  db  (Postgres :5432)         │
        │ (delayed/free EOD) │               │  named volume: pgdata         │
        └────────────────────┘               │  tables: users, accounts,     │
                                             │  positions, trades, ...,      │
                                             │  market_data_cache            │
                                             └──────────────────────────────┘
```

Key properties of this topology:

- The external market-data provider is hit **only on a cache miss**. Once a daily bar for `(ticker, date)` is stored, it is never re-fetched (historical bars are immutable). This is the primary rate-limit defense (PRD 7.3).
- The engine reads/writes the same Postgres tables that the read APIs serve. There is no separate analytics store.
- The scheduler is internal to `api`; if the `api` container is down, no runs happen (acceptable for a local single-operator MVP — no HA requirement, PRD 9.3).

---

## 2. Tech Stack Decisions

| Layer | Choice | Rationale |
|---|---|---|
| Backend framework | **FastAPI + Uvicorn** (Python 3.12) | Fixed by scaffold. Async-friendly, first-class Pydantic validation (satisfies PRD 9.1 "input validation on all write endpoints"), auto OpenAPI docs for free. |
| ORM | **SQLAlchemy 2.x** | Mature, explicit, supports `Numeric`/`DECIMAL` precision (PRD 3.4 requires fixed-point money). Lets engine + API share one model layer. |
| Migrations | **Alembic** | Standard companion to SQLAlchemy. Schema versioned in repo; `alembic upgrade head` runs on container start (Section 8). |
| Validation/serialization | **Pydantic v2** | Comes with FastAPI; defines request/response schemas in Section 5, centralizes write-side validation. |
| DB | **Postgres 16** | Fixed by `.env.example` (`POSTGRES_*`, `DATABASE_URL`). Needed for `DECIMAL(14,4)` and for safe concurrent engine-write + API-read access (PRD assumption 1 explicitly rejects SQLite for this reason). |
| Password hashing | **bcrypt via passlib** | PRD 2.2/9.1. bcrypt is the documented baseline; argon2 acceptable. Never plaintext, never logged, never returned. |
| Auth | **JWT (PyJWT)** | Fixed by scaffold (`JWT_SECRET`). HS256 access tokens (short-lived) + refresh token in HttpOnly cookie. Stateless, no session store (Section 6). |
| Scheduling | **APScheduler (in-process)** | PRD 4.6 explicitly endorses "a single shared cron-style scheduler in the backend container (e.g. APScheduler) … no separate job-queue infrastructure." See 2.4. |
| Market data | **yfinance (primary), Alpha Vantage (fallback)** behind an adapter interface | PRD 7.1 / assumption 10. yfinance needs no API key and has looser practical limits for a ~20–30 ticker daily universe. Adapter interface makes the swap a config/adapter change, not a rewrite. |
| Backtest compute | **In-process, synchronous-or-background** via the same APScheduler/threadpool | PRD 6.5 needs async "queued → running → complete" for long ranges; short ranges can run inline. No extra infra. See 2.4 + 4.6. |
| HTTP server (prod-ish) | **Uvicorn** (scaffold uses `--reload` for dev) | Keep dev `--reload` as scaffolded; production note in Section 8 (drop `--reload`, run with a couple of workers behind the single-scheduler caveat). |
| Frontend | **React 18 (CRA / react-scripts)** | Fixed by scaffold `package.json`. Do not migrate to Vite in MVP (out of scope; works as-is). |
| FE routing | **React Router v6** | Design Section 3 specifies routes + role guards mapping cleanly to React Router paths. |
| FE server-state | **TanStack Query (React Query)** | Caching, background refetch, and the polling the engine-status screen needs (design 4.10). Avoids hand-rolled fetch/loading/error state for every table. |
| FE local/UI state | **React local state + Context for auth** | No Redux needed at MVP scale; auth/session in a small Context, everything else is server state via React Query. |
| FE HTTP | **Axios** with interceptors | One place to attach the access token and implement the refresh-on-401-retry-once flow (PRD FR-12 AC3). |
| FE charts | **Recharts** | One chart type only (equity-curve line chart, design 2.4 "Charts"). Recharts is the lightest fit for a single line+area chart with hover tooltip. |
| Logging | **stdlib `logging` → stdout, structured** | PRD 9.4: structured info/warn/error to stdout, captured by `./run.sh logs`. |

### 2.4 Scheduling & background-work decision (APScheduler vs. separate worker)

**Decision: APScheduler running in-process inside the `api` container. No separate worker service, no Celery/RQ, no Redis.**

Why this is the right call for MVP:

- **Cadence is once per day.** The engine runs once after market close (PRD 4.6). This is not a high-throughput job queue; a cron-style trigger is sufficient.
- **PRD explicitly endorses it** (4.6 implementation note).
- **No fan-out concurrency need.** Signals are computed once per run, then applied across users sequentially (PRD 4.7). Tens of users × ~28 tickers completes in minutes, bounded by fetch latency, not compute (PRD 9.3).
- **Backtests** reuse the same engine code on a background thread (APScheduler's thread pool / FastAPI `BackgroundTasks`), which gives the PRD-required async "queued → running → complete" lifecycle without a broker. A `backtest_run` row is the queue.

Concurrency-control rules that this decision forces (and which the design depends on):

1. **Single-flight engine runs.** A DB-backed lock (an `engine_runs` row in status `running`, plus an advisory lock) guarantees no two engine runs overlap — required by PRD FR-6 AC2 ("manual trigger rejected if a run is already in progress").
2. **Uvicorn worker count caveat.** If `api` is run with >1 Uvicorn worker process, each process would start its own APScheduler, double-firing the cron. **MVP runs the scheduler in a single process.** For local Docker this is the default (one Uvicorn process). The advisory-lock single-flight rule in (1) is the safety net even if this is misconfigured. Documented in Section 8.

---

## 3. Data Model

All monetary columns are `DECIMAL(14,4)` (PRD 3.4) — fixed-point, never float. All timestamps are `TIMESTAMPTZ` stored in UTC; the engine's "bar date" (the trading day a trade corresponds to) is stored as a separate `DATE` where relevant (PRD 5.1). Primary keys are `BIGINT` identity (or UUID — see assumption 3). `created_at`/`updated_at` on every mutable table.

### 3.1 Entity-relationship overview (ASCII)

```
users (1) ───────── (1) accounts
  │ id                    │ user_id (FK, unique)
  │ role                  │ cash_balance
  │ is_active             │ (equity/total derived or cached)
  │
  ├── (1:N) ── fund_transactions   (audit ledger of admin funding)
  │
  ├── (1:N) ── positions           (currently OPEN holdings only)
  │
  └── (1:N) ── trades              (full BUY/SELL log, immutable)
                  │
                  └── position_id ──▶ links SELL back to its opening BUY
                  └── engine_run_id ─▶ engine_runs (which run booked it)

engine_runs (1) ── (N) trades                 (live runs only)

backtest_runs (1) ── (N) backtest_trades       (fully isolated from live tables)

market_data_cache   (ticker, bar_date) unique  (shared by engine + backtests)
```

Relationships in words:
- `users` 1:1 `accounts` (account created with the user, PRD 3.1).
- `users` 1:N `fund_transactions` (each admin top-up, PRD 3.3).
- `users` 1:N `positions` (open holdings; a closed position is deleted from this table — PRD 5.2).
- `users` 1:N `trades` (append-only history; never deleted, survives soft-delete of the user — PRD 3.2).
- `engine_runs` 1:N `trades` (which scheduled/manual run produced each trade — PRD 5.2 `engine_run_id`).
- `backtest_runs` 1:N `backtest_trades`, **completely separate** from `trades`/`positions`/`accounts` (PRD 6.4 / assumption 14 — backtests never touch live data).
- `market_data_cache` is provider-agnostic and shared by both live runs and backtests (PRD 7.3).

### 3.2 Table sketches

**`users`** — identity + role.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | |
| `email` | CITEXT/TEXT UNIQUE | case-insensitive unique; duplicate rejected (PRD 3.1) |
| `display_name` | TEXT | |
| `password_hash` | TEXT | bcrypt; never returned/logged (PRD 9.1) |
| `role` | TEXT / ENUM | `'admin'` or `'user'` |
| `is_active` | BOOLEAN | soft-delete flag (PRD 3.2); `false` blocks login |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**`accounts`** — per-user balances (1:1 with user).

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | |
| `user_id` | BIGINT FK UNIQUE → users.id | |
| `cash_balance` | DECIMAL(14,4) | uninvested virtual cash; default 0 (PRD 3.1) |
| `equity_value` | DECIMAL(14,4) | mark-to-market of open positions; recomputed each run (PRD 3.4) |
| `realized_pnl` | DECIMAL(14,4) | lifetime cumulative from closed trades |
| `updated_at` | TIMESTAMPTZ | last mark/update time (drives "as of last engine run" in design 4.2) |

`total_value` and `unrealized_pnl` are **derived** (`cash + equity`, and sum of mark − cost basis across positions). Stored vs. computed is a minor call — MVP computes `total_value` on read and caches `equity_value` after each run (assumption 5).

**`positions`** — currently open holdings only (PRD 5.2).

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | |
| `user_id` | BIGINT FK → users.id | |
| `ticker` | TEXT | indexed with user_id |
| `quantity` | INTEGER | whole shares (no fractional, PRD 4.4) |
| `entry_price` | DECIMAL(14,4) | bar-close fill (PRD 5.1) |
| `entry_date` | DATE | bar date of entry; drives days-held + max-hold (PRD 4.5) |
| `entry_trade_id` | BIGINT FK → trades.id | the opening BUY |
| `last_mark_price` | DECIMAL(14,4) | latest fetched price for unrealized P&L |
| `created_at` | TIMESTAMPTZ | |

Unique constraint `(user_id, ticker)` — enforces "no pyramiding / one open position per ticker per user" (PRD 4.4). When a position closes it is **deleted** from this table; the round-trip lives on in `trades`.

**`trades`** — append-only BUY/SELL log (PRD 5.2). Never updated or deleted.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | |
| `user_id` | BIGINT FK → users.id | indexed |
| `ticker` | TEXT | indexed |
| `side` | TEXT / ENUM | `'BUY'` / `'SELL'` |
| `quantity` | INTEGER | |
| `price` | DECIMAL(14,4) | bar-close fill price (PRD 5.1) |
| `trade_value` | DECIMAL(14,4) | `quantity * price` |
| `executed_at` | TIMESTAMPTZ | engine-run timestamp; indexed |
| `bar_date` | DATE | the trading day the fill corresponds to (PRD 5.1) |
| `signal_reason` | TEXT / ENUM | `ENTRY_TREND_MOMENTUM`, `EXIT_PROFIT_TARGET`, `EXIT_STOP_LOSS`, `EXIT_MAX_HOLD`, `EXIT_TREND_INVALIDATION` (PRD 5.2) |
| `realized_pnl` | DECIMAL(14,4) NULL | populated on SELL only; NULL on BUY (design 4.3 renders `—` for NULL) |
| `position_id` | BIGINT NULL | links SELL→opening BUY round-trip (PRD 5.2) |
| `engine_run_id` | BIGINT FK → engine_runs.id | audit link (PRD 5.2) |

Indexes: `(user_id, executed_at DESC)` for the newest-first history view; `(user_id, ticker)` for the ticker filter; `(executed_at)` / `(engine_run_id)` for the admin "trades today" view (PRD 9.3 names these).

**`fund_transactions`** — admin funding audit ledger (PRD 3.3). Separate from trade history.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | |
| `user_id` | BIGINT FK → users.id | funded account |
| `admin_id` | BIGINT FK → users.id | which admin performed it |
| `amount` | DECIMAL(14,4) | must be `> 0` (PRD FR-4 AC2) |
| `resulting_balance` | DECIMAL(14,4) | cash_balance after this top-up |
| `created_at` | TIMESTAMPTZ | |

**`engine_runs`** — one row per scheduled or manual run; the operational/observability record (PRD 4.6, 9.4).

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | shown as "Run #" in design 4.10 |
| `trigger` | TEXT / ENUM | `'scheduled'` / `'manual'` |
| `status` | TEXT / ENUM | `'running'` / `'complete'` / `'failed'` |
| `started_at` | TIMESTAMPTZ | |
| `finished_at` | TIMESTAMPTZ NULL | |
| `tickers_evaluated` | INTEGER | run summary (PRD 4.6) |
| `signals_fired` | INTEGER | |
| `trades_executed` | INTEGER | |
| `users_affected` | INTEGER | |
| `errors` | JSONB | per-ticker fetch failures etc. (PRD 7.3); empty array = clean run |

The single `status = 'running'` row + a Postgres advisory lock is the single-flight mechanism (Section 2.4, PRD FR-6 AC2).

**`backtest_runs`** — admin strategy-evaluation runs (PRD 6.2–6.4). Isolated from live data.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | |
| `created_by` | BIGINT FK → users.id | admin who ran it |
| `start_date` / `end_date` | DATE | validated `end > start`, within provider range (PRD FR-7 AC2) |
| `tickers` | JSONB | subset or full universe (PRD 6.2) |
| `starting_capital` | DECIMAL(14,4) | default 100000 (PRD 6.2) |
| `status` | TEXT / ENUM | `'queued'` / `'running'` / `'complete'` / `'failed'` (PRD 6.5) |
| `total_return_pct` / `total_return_abs` | DECIMAL | result summary (PRD 6.4) |
| `win_rate` | DECIMAL | |
| `total_trades` | INTEGER | |
| `max_drawdown_pct` / `max_drawdown_abs` | DECIMAL | |
| `avg_holding_days` | DECIMAL | sanity-checks 1–2 week behavior (PRD 6.4) |
| `equity_curve` | JSONB | array of `{date, total_value}` for the chart (PRD 6.4) |
| `created_at` / `finished_at` | TIMESTAMPTZ | |

**`backtest_trades`** — per-trade log for a backtest, same shape as `trades`, scoped by `backtest_run_id` (PRD 6.4 / assumption 14).

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | |
| `backtest_run_id` | BIGINT FK → backtest_runs.id | |
| `ticker`, `side`, `quantity`, `price`, `trade_value`, `bar_date`, `signal_reason`, `realized_pnl` | (same types as `trades`) | never references a real user (assumption 14) |

**`market_data_cache`** — immutable daily bars (PRD 7.3). Shared by engine + backtests.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK | |
| `ticker` | TEXT | |
| `bar_date` | DATE | |
| `open` / `high` / `low` / `close` | DECIMAL(14,4) | OHLC (PRD 7.2) |
| `volume` | BIGINT | |
| `provider` | TEXT | `'yfinance'` / `'alphavantage'` — which source supplied it |
| `fetched_at` | TIMESTAMPTZ | |

Unique constraint `(ticker, bar_date)` — write-once, never re-fetch a cached date (PRD 7.3). This is the core rate-limit defense.

> **Watchlist / strategy params are config, not tables** (PRD 4.2/assumption 2,3,13): the tradable universe and the strategy constants (SMA windows, RSI band, sizing %, position cap, target/stop/max-hold) live in backend config (env or a `config.py` module), not user-editable in MVP.

---

## 4. Trading Engine Design

### 4.1 One engine, computed once, applied per user

The engine is a single Python module with a pure **signal layer** (market-data → BUY/SELL decisions, no user state) and an **apply layer** (decisions + a given account's cash/positions/slots → concrete trades). PRD 4.7 requires signals be computed **once per run** and then applied identically across every active user. This split is what makes that literal:

```
run_engine(engine_run_id, as_of_date, accounts):
    # ── SIGNAL LAYER (once per run, user-independent) ──
    bars = market_data.get_daily_bars(universe, lookback)   # cache-first
    indicators = compute_indicators(bars)                    # SMA20/50, RSI14, EMA10
    buy_signals  = entry_signals(indicators)                 # PRD 4.3
    # exit *conditions* are per-position, evaluated in the apply layer

    # ── APPLY LAYER (per active user, order matters) ──
    for account in active_accounts(accounts):                # PRD 4.7
        # 1. EXITS FIRST so cash/slots free up before entries (PRD 4.6 step 2)
        for pos in open_positions(account):
            reason = check_exit(pos, indicators, as_of_date)  # PRD 4.5
            if reason: sell(account, pos, price=bar_close, reason)
        # 2. ENTRIES, respecting this user's cash + slot constraints
        for sig in buy_signals:
            if eligible(account, sig):                        # PRD 4.4 sizing/slot/dup rules
                buy(account, sig, price=bar_close, reason=ENTRY_TREND_MOMENTUM)
    finalize_run(engine_run_id, summary)                      # PRD 4.6 step 4
```

### 4.2 Activation per funded user

There is no "activate" toggle. On each run the engine selects accounts where `is_active = true AND (cash_balance + equity_value) > 0` (PRD 3.3 activation rule). The first funding transaction that pushes a $0 user above zero makes them eligible on the **next** run — funding *is* activation (PRD 3.3, FR-4 AC3). Deactivated users are skipped, and their open positions simply stop updating (PRD 3.2, assumption 7 — no auto-liquidation).

### 4.3 Signal logic (config-driven, PRD 4.3–4.5)

- **Entry (all three must hold on the same run):** SMA20 > SMA50 (trend filter), RSI14 in [50,70] (momentum, not overbought), and EMA10-crosses-above-SMA20 within the last trading day (trigger). → `ENTRY_TREND_MOMENTUM`.
- **Sizing:** `floor((cash_balance * 0.10) / bar_close)` shares per position; max 5 concurrent positions/user; skip if already holding the ticker, if slot cap hit, or if cash insufficient (PRD 4.4). No fractional shares, no pyramiding.
- **Exit (first to trigger wins, checked every run):** +8% profit target / −4% stop / 10-trading-day max hold / SMA20-crosses-below-SMA50 trend invalidation (PRD 4.5). → the matching `EXIT_*` reason.

All thresholds are config constants (assumption 2), referenced by both live and backtest paths.

### 4.4 Decisions → recorded trades & fills

Every BUY/SELL fills at the **close of the bar that triggered it** (PRD 5.1 — zero slippage/commission, MVP idealization). Each fill:
1. Inserts a `trades` row (with `engine_run_id`, `signal_reason`, `bar_date`, and for SELLs the `realized_pnl` and `position_id` of the round-trip).
2. Mutates `positions` (insert on BUY, delete on SELL).
3. Adjusts `accounts.cash_balance` (and `realized_pnl` on SELL).
4. After all users processed, recomputes each touched account's `equity_value` from the latest marks.

All of (1)–(4) for a single account happen in **one DB transaction** so a partial fill can't corrupt the ledger (Section 7.2).

### 4.5 Scheduling / cadence

APScheduler fires a daily cron job at **17:00 US/Eastern** (after the 16:00 ET close + data settle, PRD 4.6). The job creates an `engine_runs` row (`trigger='scheduled'`), takes the advisory lock, runs `run_engine`, and finalizes the summary. The admin "Trigger Run Now" endpoint calls the **same** `run_engine` with `trigger='manual'` (PRD FR-6 AC1) and is rejected with `409 Conflict` if a run is already `running` (FR-6 AC2). Per-ticker fetch failures are caught, logged, appended to `engine_runs.errors`, and the run continues — a single bad ticker does not fail the run (PRD 7.3; run stays `complete`, not `failed`).

### 4.6 Simulation mode reuses the same code

The backtest **calls the identical signal + exit + sizing functions** (PRD 6.3 / 4.7), but:
- Iterates a date range day-by-day over cached historical bars (bulk-fetched once per ticker per run, PRD 7.3) instead of running once "today."
- Seeds a single in-memory virtual account with `starting_capital` instead of reading real `accounts`.
- Writes only to `backtest_runs` / `backtest_trades` — never to `trades`/`positions`/`accounts` (assumption 14).
- Runs on a background thread; status transitions `queued → running → complete|failed` (PRD 6.5). On completion it computes and stores equity curve, total return, win rate, trade count, max drawdown, avg holding period (PRD 6.4).

Because the same fill convention (bar close), sizing (10%/5-cap), and rules are used, live and backtest math are guaranteed to agree (PRD 6.3) — they are literally the same functions.

---

## 5. API Contracts

Conventions: JSON bodies; access token in `Authorization: Bearer <jwt>`; errors return `{ "detail": "<message>" }` with standard HTTP codes (`400` validation, `401` unauthenticated/expired, `403` wrong role, `404` not found, `409` conflict). Money is sent/received as decimal strings to avoid float drift. `/me/*` routes derive scope from the token's `user_id` and **ignore any client-supplied user id** (PRD FR-12 AC2).

### 5.1 Auth

| Method | Path | Auth | Body / Response |
|---|---|---|---|
| POST | `/auth/login` | public (throttled) | req `{email, password}` → `{access_token, role, user_id}` + sets `refresh_token` HttpOnly cookie. `401` generic "Invalid email or password" (FR-8 AC2); `403` "account disabled" for `is_active=false` (FR-8 AC3) |
| POST | `/auth/refresh` | refresh cookie | reads HttpOnly cookie → `{access_token}`; `401` if missing/expired |
| POST | `/auth/logout` | any authed | clears refresh cookie → `204` |
| GET | `/auth/me` | any authed | `{user_id, email, display_name, role, is_active}` (for shell header, design 3.2) |

### 5.2 Admin — user management (`role == admin`, else `403` per FR-12 AC1)

| Method | Path | Body / Response |
|---|---|---|
| GET | `/admin/users?status=active|deactivated&q=&page=&page_size=` | paginated `{items:[{id,display_name,email,role,is_active,total_value}], total}` (design 4.5) |
| POST | `/admin/users` | req `{email, display_name, password, role}` → `201 {id,...}`; `400` weak password / bad email; `409` duplicate email (FR-2 AC2) |
| GET | `/admin/users/{id}` | full inspector payload `{user, account, positions[], ...}` (design 4.8); works for deactivated users (FR-5 AC2) |
| DELETE | `/admin/users/{id}` | soft-delete: sets `is_active=false` → `200`; `409` if last active admin (assumption 8 / PRD 10.8) |
| POST | `/admin/users/{id}/fund` | req `{amount}` (decimal string, `>0`) → `200 {new_balance}` + writes `fund_transactions`; `400` if `<= 0` (FR-4 AC2) |

### 5.3 Account / portfolio (self-service)

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/me/account` | user/admin | `{cash_balance, equity_value, total_value, realized_pnl, unrealized_pnl, as_of}` (FR-9); zero-state when total = 0 (FR-9 AC2) |
| GET | `/me/positions` | user/admin | `[{ticker, quantity, entry_price, entry_date, days_held, current_price, unrealized_pnl_abs, unrealized_pnl_pct}]` (FR-10) |

Admin viewing another user reuses `/admin/users/{id}` (same payload, design 4.8) — no separate per-user portfolio endpoints needed.

### 5.4 Trade history

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/me/trades?ticker=&from=&to=&page=&page_size=` | user/admin | paginated, newest-first; row = PRD 5.2 fields; `realized_pnl` NULL on BUY (FR-11). Scope strictly token-derived (FR-11 AC3) |
| GET | `/admin/users/{id}/trades?...` | admin | same shape, any user (FR-5) |
| GET | `/admin/trades-today?ticker=&side=&user_id=` | admin | cross-user feed for today's run + summary `{trades, users_evaluated, signals_skipped, errors}` (design 4.9); optional CSV export |

### 5.5 Engine (admin)

| Method | Path | Response |
|---|---|---|
| GET | `/admin/engine/status` | `{state: idle|running, last_run, next_scheduled_run, progress?}` — polled while running (design 4.10) |
| POST | `/admin/engine/run` | triggers manual run → `202 {engine_run_id}`; `409` if a run is in progress (FR-6 AC2) |
| GET | `/admin/engine/runs?page=` | paginated run history (design 4.10) |
| GET | `/admin/engine/runs/{id}` | full run detail incl. per-ticker breakdown + `errors[]` (PRD 4.6, 7.3) |

### 5.6 Backtests (admin)

| Method | Path | Response |
|---|---|---|
| POST | `/admin/backtests` | req `{start_date, end_date, tickers?, starting_capital?}` → `202 {backtest_run_id, status:"queued"}`; `400` if `end<=start` or out of provider range (FR-7 AC2) |
| GET | `/admin/backtests?page=` | list past runs with params + headline metrics (FR-7 AC3, design 4.12) |
| GET | `/admin/backtests/{id}` | full result: status, summary metrics, `equity_curve[]`, and `backtest_trades[]` (PRD 6.4) |

### 5.7 Market data (internal-leaning, admin)

| Method | Path | Response |
|---|---|---|
| GET | `/admin/market-data/range` | `{earliest, latest}` provider range, backing the backtest form's "Available data" hint (design 4.11) |
| GET | `/admin/market-data/universe` | the configured watchlist tickers (design 4.11 subset picker) |

Live quote fetching for the dashboard is done **server-side during the engine run** (marks stored on `positions`/`accounts`); the frontend never calls the market provider directly. There is no public market-data endpoint.

---

## 6. Authentication & Authorization

### 6.1 JWT flow

```
Login ──▶ POST /auth/login {email,password}
            │ verify is_active, verify bcrypt hash
            ▼
        issue access_token (HS256, ~30 min, claims: sub=user_id, role, exp)
        issue refresh_token (~7 days) ──▶ Set-Cookie: refresh_token (HttpOnly, SameSite=Lax, Secure-in-prod)
            │
            ▼
Client stores access_token in memory (not localStorage — XSS hardening, assumption 9)
            │
Every API call ──▶ Authorization: Bearer <access_token>
            │
On 401 (expired) ──▶ Axios interceptor calls POST /auth/refresh (cookie) ──▶ new access_token ──▶ retry once
            │  (FR-12 AC3)
On refresh failure ──▶ clear state, redirect /login?next=<path>
```

- **Access token**: short-lived HS256 JWT signed with `JWT_SECRET` (from `.env`, never committed). Claims: `sub` (user_id), `role`, `exp`. Stateless — no server session store (PRD 2.2).
- **Refresh token**: longer-lived, delivered as an **HttpOnly cookie** so JS can't read it (mitigates XSS token theft). Used only by `/auth/refresh`.

### 6.2 Roles & route protection

Two roles in the `role` claim: `admin`, `user` (PRD 2.1). Enforcement is **server-side** via FastAPI dependencies (PRD 9.1 — never rely on the frontend hiding a button):

- `require_auth` — decodes/validates the JWT, rejects expired (`401`) and inactive users; injects the current user.
- `require_admin` — additionally asserts `role == 'admin'`, else `403` (FR-12 AC1). Applied to every `/admin/*` route.
- `/me/*` routes use **only** the token's `user_id` for data scope; any `user_id` in body/query is ignored (FR-12 AC2). This is the single defense against cross-account data leaks (FR-11 AC3).

Frontend route guards (React Router) mirror this for UX (`user` hitting `/admin/*` → redirect to `/dashboard`, design 3.4), but are **never** the security boundary — the server check is authoritative.

### 6.3 Admin bootstrap (PRD 2.3, FR-1)

On `api` startup, after migrations: if no `role='admin'` user exists, seed exactly one from `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD` env vars. Idempotent (never duplicates once an admin exists — FR-1 AC2). If the env vars are absent and no admin exists, log a clear warning and skip (FR-1 AC3 — documented, not silent). After bootstrap, that admin creates further users/admins via `POST /admin/users`.

### 6.4 Login throttling (PRD 9.1)

Lightweight per-IP + per-email failure counter (in-memory or a small Postgres table) that locks out after N rapid failures for a cooldown window. Not a WAF — just enough to blunt brute-force (assumption 6).

---

## 7. Data Flow

### 7.1 Representative user action — "load my dashboard"

```
1. Browser hits /dashboard (React route, guard checks in-memory access token)
2. React Query fires GET /me/account and GET /me/positions with Bearer token
3. api: require_auth decodes JWT → user_id; ignores any client-sent id
4. Service reads accounts + positions for THAT user_id from Postgres
5. unrealized P&L / total_value computed from stored marks (last engine run)
6. Response JSON → React renders stat cards + positions panel
   - if total_value == 0 → zero-state card (FR-9 AC2)
   - if access token expired → 401 → interceptor refreshes once → retry (FR-12 AC3)
   - if last price fetch had failed → stale-data banner using last-known marks (design 4.2)
```

### 7.2 Engine trade cycle (scheduled run)

```
1. APScheduler fires @ 17:00 ET → create engine_runs row (status=running)
2. Acquire advisory lock (single-flight; manual trigger meanwhile → 409, FR-6 AC2)
3. SIGNAL LAYER (once):
   a. For each universe ticker: market_data.get_daily_bars()
      - cache hit  → read market_data_cache
      - cache miss → fetch yfinance → write cache (immutable)
      - fetch error → log, append to engine_runs.errors, SKIP ticker (PRD 7.3)
   b. compute indicators → entry BUY signals
4. APPLY LAYER (per active user, each in ONE DB transaction):
   a. exits first (free cash/slots) → SELL fills, update positions/cash/realized_pnl
   b. entries → size 10%, respect 5-slot cap + dup-ticker skip → BUY fills
   c. recompute equity_value for the account
5. finalize engine_runs: status=complete, counts, errors[], finished_at
6. Release lock. Dashboards now reflect new marks on next read (no push; design is poll/refresh)
```

A run failure mid-way (e.g. DB down) rolls back the in-flight account transaction and marks the run `failed`; already-committed per-account transactions stand (each account is its own atomic unit), so the run is resumable/auditable rather than all-or-nothing across users.

---

## 8. Deployment Strategy

### 8.1 Local Docker Compose (v1 — the only supported deployment)

Three services. The scaffold currently defines `api` + `frontend`; **add a `db` service + named volume** (the `.env.example` already scaffolds the `POSTGRES_*` / `DATABASE_URL` values for it):

```
services:
  api:
    build: ./api
    ports: ["8000:8000"]
    volumes: ["./api:/app"]          # live-reload dev mount (scaffold)
    env_file: .env
    depends_on:
      db:
        condition: service_healthy   # wait for DB before migrations
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    volumes: ["./frontend:/app", "/app/node_modules"]   # scaffold
    env_file: .env
    depends_on: [api]
    restart: unless-stopped

  db:                                 # NEW — to be added
    image: postgres:16
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: ["pgdata:/var/lib/postgresql/data"]   # persistence (PRD 9.2)
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      retries: 10
    restart: unless-stopped

volumes:
  pgdata:
```

- **Startup sequence**: `db` healthy → `api` runs `alembic upgrade head` then admin-bootstrap seed (Section 6.3) then `uvicorn main:app` → `frontend` `npm start`. The migrate+seed step runs in the `api` container entrypoint (or a small `start.sh`), not in `main.py` import time.
- **Env**: single `.env` (gitignored) consumed by all services. Required keys: `DATABASE_URL`, `POSTGRES_*`, `JWT_SECRET`, `ADMIN_BOOTSTRAP_EMAIL`, `ADMIN_BOOTSTRAP_PASSWORD`. `MARKET_DATA_API_KEY` only needed if the Alpha Vantage fallback is enabled (yfinance needs none — PRD 7.1).
- **Volumes**: `pgdata` named volume for DB persistence (survives `down`/rebuild, PRD 9.2). The `./api` and `./frontend` bind mounts are dev-only conveniences (hot reload), already in the scaffold.
- **Run**: via the workspace-standard `./run.sh` (start/up/stop/restart/logs/build/status/test/shell/clean/help) wrapping `docker compose`. `./run.sh logs` is the observability surface (PRD 9.4).
- **CRA dev proxy**: the React app proxies `/api`/auth calls to `api:8000` (CRA `proxy` field or an explicit `REACT_APP_API_BASE`), so the browser talks to one origin and the refresh cookie stays first-party.

### 8.2 Scheduler caveat in deployment

Keep `api` to a **single Uvicorn process** in MVP so only one APScheduler instance exists (Section 2.4). The scaffold's dev `--reload` already runs a single worker. If a future production setup adds workers, move the scheduler to a dedicated single-instance process or rely on the DB advisory lock (already implemented) to keep runs single-flight.

### 8.3 Future cloud path (out of scope for v1, noted only)

Consistent with the workspace pattern (local Docker Compose now, cloud later) and PRD 1.4/9.2/assumption 12. When/if cloud is pursued: containerize the same images to a managed runtime (e.g. Cloud Run / ECS / Fly), move Postgres to a managed instance (RDS / Cloud SQL), extract the scheduler+engine into its own single-instance worker (so the API can scale horizontally while the engine stays single-flight), serve the React build as static assets behind a CDN, and add backups/DR (explicitly deferred in MVP, assumption / PRD 9.2). No cloud work is done in v1.

---

## 9. Security Considerations & Open Risks

### 9.1 Controls in MVP (mapped to PRD 9.1)

- **Password storage**: bcrypt hashes only; never logged, never in any response (PRD 9.1).
- **Secrets**: `JWT_SECRET`, DB creds, any market API key from `.env` only; `.env` gitignored; nothing hardcoded (PRD 9.1).
- **RBAC server-side**: `require_admin` on every `/admin/*` route (`403` for `user`, FR-12 AC1); `/me/*` scope derived solely from token (FR-12 AC2). Frontend guards are UX-only.
- **Token hygiene**: short-lived access token held in memory (not localStorage), refresh token in HttpOnly cookie (limits XSS theft); `Secure` + `SameSite` on the cookie in any non-local deployment.
- **Input validation**: Pydantic schemas reject bad input (fund amount > 0, email format, date ranges, password min length) with `4xx` before touching the DB (PRD 9.1, FR-2/FR-4/FR-7 ACs).
- **Login throttling**: per-IP/per-email lockout to blunt brute force (PRD 9.1).
- **Account-enumeration resistance**: login returns a generic message regardless of whether the email exists (FR-8 AC2); deactivated accounts get a distinct message only after credentials validate (FR-8 AC3) — a deliberate, accepted nuance.
- **Last-admin lockout guard**: block deactivating the final active admin (assumption / PRD 10.8).
- **Backtest isolation**: backtests write only to `backtest_*` tables; structurally cannot mutate real user data (assumption 14).

### 9.2 Accepted risks / non-goals (MVP)

- **No HTTPS locally** — local Docker over HTTP is acceptable for a single-operator tool; `Secure` cookies + TLS are a cloud-phase concern.
- **No backups/DR** — local single-operator MVP (PRD 9.2 / assumption 12); the `pgdata` volume is the only durability guarantee.
- **No CSRF token for the refresh cookie** — mitigated by `SameSite=Lax` + the access token being a Bearer header (not cookie-auth) for state-changing routes; revisit if cookie-based auth expands.
- **yfinance is an unofficial endpoint** — can break or rate-limit without notice (PRD 7.1). Mitigated by the immutable cache (most reads never hit it) and the Alpha Vantage adapter fallback; a hard outage degrades to "today's ticker skipped," surfaced in the run log, not a crash (PRD 7.3).
- **No audit log beyond `fund_transactions` + `engine_runs`** — admin actions like user creation/deactivation are not separately audited in MVP; acceptable for a closed, admin-only-created user base.
- **No rate limiting beyond login** — the API trusts authenticated users; acceptable for tens of known users on a local deployment (PRD 9.3).

---

## 10. Assumptions

Decisions made where the PRD/design/scaffold were silent, chosen to keep the MVP buildable without re-opening locked requirements. Each is a reasonable default to be revisited deliberately later.

1. **Three Compose services** (`api`, `frontend`, `db`). The scaffold only commits `api` + `frontend`; a `db` Postgres service + `pgdata` volume must be added (the `.env.example` already anticipates it). No other services (no Redis/broker/worker) — APScheduler in-process covers scheduling.
2. **APScheduler in-process** is the scheduling mechanism (PRD 4.6 endorses it); the engine + market-data adapter are modules inside `api`, not separate containers. Single Uvicorn process in MVP to avoid double-scheduling; a DB advisory lock enforces single-flight regardless.
3. **PK type** is BIGINT identity (UUIDs are fine too); not load-bearing — implementation may pick either consistently.
4. **`equity_value` is cached on `accounts`** after each run and `total_value`/`unrealized_pnl` are computed on read; alternatively all could be derived live. Either is acceptable at MVP scale.
5. **Money over the wire as decimal strings** to avoid JSON float drift, matching the `DECIMAL(14,4)` storage; the frontend rounds to 2dp at render only (design 6).
6. **Login throttle** is a lightweight in-memory/DB counter, not a distributed limiter — adequate for a single local instance.
7. **Access token in memory, refresh token in HttpOnly cookie** — chosen over localStorage for XSS hardening; PRD 2.2 specifies the refresh-cookie pattern, this fills in the access-token storage detail.
8. **Migrate + seed run in the `api` entrypoint** (e.g. `start.sh`: `alembic upgrade head` → bootstrap seed → uvicorn), not at module import, so startup ordering against `db` health is explicit.
9. **CRA stays** (no Vite migration); React Router v6, TanStack Query, Axios, Recharts are the chosen FE libs filling the scaffold's bare `react`/`react-dom`/`react-scripts`.
10. **yfinance is the concrete primary** data source behind a provider interface; Alpha Vantage is the config-swappable fallback (PRD 7.1 / PRD assumption 10). `MARKET_DATA_API_KEY` in `.env` is only consumed by the fallback.
11. **Watchlist + strategy constants are backend config** (env/`config.py`), not DB tables and not admin-editable in MVP (PRD assumption 2,3,13).
12. **Engine runs at 17:00 US/Eastern**; the `api` container's timezone handling must convert correctly (store UTC, schedule in ET). The exact minute is config.
13. **No WebSocket/push**; the engine-status screen and dashboards refresh via polling/refetch (design 4.2, 4.10) — no real-time transport needed given the daily cadence.
14. **CSV export for "trades today"** (design 4.9) is generated server-side on demand; no separate export pipeline.
