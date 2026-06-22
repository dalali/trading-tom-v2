# PRD: trading-tom-v2

**Status:** Locked for MVP build
**Owner:** Bet Buddy PM (acting as product owner)
**Last updated:** 2026-06-22

---

## 1. Overview & Goals

### 1.1 What this is

trading-tom-v2 is a multi-user **paper-trading** platform for US equities. Users hold virtual cash balances funded by an Admin. A single, shared, automated trading engine trades on behalf of every funded user using the same strategy and the same signals — users do not pick stocks, configure parameters, or place manual orders. The product's value is letting multiple people observe and compare how one trading strategy performs against real (delayed) market data, using their own virtual account as the ledger.

This is **not** a brokerage, not connected to any real brokerage or bank, and never risks real money. There is no manual order entry, no portfolio customization per user, and no real-money settlement anywhere in the system.

### 1.2 Goals (MVP)

1. An Admin can create user accounts, delete user accounts, and load virtual cash into any user's account.
2. The moment a user has a positive virtual cash balance, the shared trading engine begins trading on their account automatically, using the same logic applied to every other funded user.
3. Every simulated trade (entry and exit) is recorded against the specific user account that owns it, and that user can see their own full trade history and current positions/balance.
4. Admin can run a backtest/simulation of the trading engine against historical data to evaluate strategy performance independent of any live user account.
5. Market data (current/recent prices, historical daily OHLCV) comes from a free, delayed-tier API — no paid real-time feed.
6. The whole system runs locally via Docker Compose for v1. No cloud deployment.

### 1.3 Why one shared engine, not per-user strategies

This is a deliberate product decision, not a limitation to revisit casually: the platform is meant to showcase and evaluate **one** strategy's behavior across many accounts/observers, not to be a multi-strategy backtesting sandbox or a user-configurable bot platform. Per-user strategy configuration is explicitly out of scope (see Non-Goals). If that need emerges later, it is a v3+ direction, not an MVP gap.

### 1.4 MVP Scope Boundaries

**In scope (v1 / MVP):**
- Admin and Regular User roles with login and role-based access control.
- Admin bootstrap (first admin account), user CRUD (create/delete — no "edit" beyond funding), and virtual fund loading.
- One shared trading engine implementing a daily/swing strategy (1–2 week holds) described in Section 4.
- Trading engine runs on a schedule (not on-demand by users) and applies identically to all funded accounts.
- Per-user trade history, open positions, and balance view.
- Admin-only backtest/simulation tool against historical data, with summary performance output (P&L, win rate, drawdown, equity curve).
- Integration with one free/delayed market data API (yfinance as primary choice — see Section 7) for both live signal generation and historical backtest data.
- Local deployment via Docker Compose (Python backend + React frontend, per existing scaffold).
- Basic persistence (relational DB) so data survives container restarts.

**Out of scope (v1 / MVP) — explicit non-goals:**
- Any real brokerage integration, real order routing, or real money movement of any kind.
- Cloud deployment, multi-region, autoscaling, or managed hosting. v1 is local Docker Compose only.
- Per-user strategy selection/configuration, manual trade entry, or watchlists.
- Real-time/low-latency intraday data or sub-minute decisioning. The engine is explicitly daily/swing, not HFT or scalping.
- Options, futures, crypto, forex, or non-US-equity instruments.
- Short selling, margin, leverage. All positions are simple long-only paper positions.
- Mobile apps (web responsive UI only).
- Email/SMS notifications, password-reset-via-email flows (see Section 2 for the simplified auth model).
- Multi-admin permission tiers (all admins have identical, full admin rights).
- Tax/PnL reporting for real-world tax purposes (this is a paper system; any P&L is illustrative only).
- Social/sharing features (leaderboards, comparing users to each other) — noted as a plausible v2 idea but not built now.

---

## 2. User Roles & Auth Model

### 2.1 Roles

| Role | Capabilities |
|---|---|
| **Admin** | Create users, delete users, load/adjust virtual funds into any user account, view all users' trade histories and balances, run backtests/simulations, view engine status/logs. Cannot place manual trades — the engine trades for everyone, admin included if admin also holds a funded account. |
| **Regular User** | Log in, view own account balance, own positions, own full trade history. Read-only with respect to trading — cannot place, modify, or cancel trades, cannot change the strategy, cannot fund their own account. |

There is no "unfunded user" capability beyond login and viewing an empty/zero state — a user with $0 virtual balance sees their dashboard but the engine takes no action on their account (nothing to size positions with).

### 2.2 Auth model

- **Credentials:** username/email + password. Passwords hashed with bcrypt (or equivalent, e.g. argon2) — never stored in plaintext.
- **Session mechanism:** JWT access tokens (short-lived, e.g. 15–60 min) issued on login, returned to the client, sent as `Authorization: Bearer <token>` on API calls. A refresh token (longer-lived, e.g. 7 days), stored as an HttpOnly cookie, is used to mint new access tokens without re-login. This is a standard stateless pattern appropriate for a small local-first app — no separate session store required for MVP.
- **RBAC:** Each JWT carries a `role` claim (`admin` or `user`) and a `user_id`. Backend middleware enforces role checks per route (e.g. `/admin/*` routes require `role == admin`). There is no resource-level ACL beyond "a regular user can only ever read their own user_id's data" — enforced by deriving the target user_id from the token, never trusting a client-supplied user_id for "my data" endpoints.
- **No self-service signup.** Regular User accounts are created exclusively by an Admin (Section 3). There is no public registration page. This is intentional: it keeps the platform closed and controllable, consistent with "Admin creates and deletes users."
- **No email-based password reset for MVP.** Admin can reset a user's password directly (sets a new temporary password the admin relays to the user out-of-band). This avoids needing an email/SMS provider for v1. Flagged as an assumption in Section 10.

### 2.3 Admin bootstrap

A fresh deployment has zero users in the database. The first Admin account must be creatable without any existing Admin to authorize it. Mechanism:

- On first backend startup, a seed step checks if any user with `role == admin` exists in the DB.
- If none exists, the backend creates exactly one Admin account using credentials supplied via environment variables (`ADMIN_BOOTSTRAP_EMAIL`, `ADMIN_BOOTSTRAP_PASSWORD`) read from `.env`. If these env vars are absent, the backend logs a clear startup warning and skips seeding (the operator must set them and restart).
- This seed step is idempotent — it never overwrites or duplicates an admin on subsequent restarts once at least one admin exists.
- After bootstrap, that Admin can create additional Admins or Regular Users through the normal "create user" endpoint (Section 3), with a `role` field selectable only by an existing Admin.

This keeps bootstrap simple, scriptable, and consistent with the existing `.env.example` / `run.sh` pattern already in the repo scaffold — no separate CLI tool or manual DB insert required.

---

## 3. User & Account Management

### 3.1 Create user (Admin action)

Admin submits: email, display name, initial role (`user` or `admin`), and an initial password (admin sets it directly — no invite-email flow, consistent with Section 2.2). System creates:
- A `users` record (id, email, display name, role, hashed password, created_at, is_active).
- A linked `accounts` record (1:1 with user) initialized with `cash_balance = 0.00`, `equity_value = 0.00` (market value of open positions), `total_value = cash_balance + equity_value`.

A new user with `cash_balance = 0` is **not** traded by the engine (see 3.3). Email must be unique; duplicate email is rejected with a clear error.

### 3.2 Delete user (Admin action)

- Admin can delete any Regular User or Admin account (except — see Assumptions, Section 10, on whether self-deletion / last-admin deletion is blocked).
- Deletion is a **soft delete** (`is_active = false`, login disabled) rather than a hard row delete, so historical trade records remain intact for audit/reporting integrity and don't orphan foreign keys. The user disappears from "active users" lists but an Admin can still view their historical trade log if needed.
- On deletion: any open positions for that user are **not** auto-liquidated by default — see Assumptions (this is a real product decision worth flagging explicitly, default chosen: positions are left open in the data model but the engine skips processing for inactive users going forward, so a deleted user's open position simply stops updating). This avoids the engine secretly closing positions at a moment the admin didn't intend.
- Deleted/deactivated users cannot log in (auth check rejects `is_active = false` even with valid credentials).

### 3.3 Fund account with virtual cash (Admin action)

- Admin selects a user and submits a positive dollar amount to add to that user's `cash_balance`. This is strictly additive top-up for MVP — no "withdraw" or "set balance to X" operation (simplest model; see Assumptions).
- Each funding action creates a `fund_transactions` ledger record (user_id, admin_id who performed it, amount, timestamp, resulting_balance) — this is an audit trail, separate from trade history.
- **Engine activation rule:** the trading engine considers a user "active for trading" if `cash_balance + equity_value > 0` AND `user.is_active = true`. The very first funding transaction that takes a user's total above $0 is what flips them from dormant to live on the next scheduled engine run — there is no separate "activate" toggle; funding *is* activation. This directly satisfies the locked requirement "once a user is funded, the trading engine activates for that user."
- There is no minimum funding amount enforced for MVP beyond "> 0", but the UI will suggest sensible amounts (e.g. preset buttons for $1,000 / $10,000 / $100,000) to streamline the common case.

### 3.4 Account balance model

Each user's account tracks:
- `cash_balance`: uninvested virtual dollars, available for the engine to size new positions with.
- `positions`: list of currently open holdings (ticker, quantity, entry price, entry date) — see Section 5.
- `equity_value`: current mark-to-market value of all open positions, recomputed at each engine tick using the latest fetched price.
- `total_value` = `cash_balance + equity_value` — this is the headline number shown on the user's dashboard.
- `realized_pnl` (lifetime, cumulative): sum of profit/loss from all closed trades.
- `unrealized_pnl`: sum of (current mark value − cost basis) across open positions.

All monetary values stored as fixed-point (e.g. `DECIMAL(14,4)` in Postgres), never floating point, to avoid rounding drift across many simulated trades.

---

## 4. Trading Engine

### 4.1 Design intent

One engine, one rule set, applied identically to every funded account, every scheduled run. The engine is a **daily-swing trend/momentum strategy**: it looks for established short-term trends with momentum confirmation, enters with a sized position, and exits on a fixed rule set (target, stop, or max holding period) — whichever triggers first. This is intentionally a well-understood, explainable strategy (not ML/black-box) so its behavior is auditable and its backtest results are interpretable.

### 4.2 Universe (tradable tickers)

The engine does not scan the entire US market. MVP uses a **fixed, curated watchlist** of liquid, large-cap US equities/ETFs (e.g. 20–30 tickers — large S&P 500 names plus 1–2 broad ETFs like SPY/QQQ). Rationale: free/delayed data tiers have rate limits (Section 7); scanning thousands of tickers daily is neither necessary for an MVP nor reliable on a free API quota. The watchlist is a backend config list (not user-editable in MVP) — see Assumptions for whether Admin can edit it later.

### 4.3 Signal logic (entry)

For each ticker in the universe, on each scheduled engine run, using daily OHLCV bars:

1. **Trend filter:** 20-day SMA > 50-day SMA (short-term uptrend confirmed against medium-term trend). This is the primary directional gate — the strategy is long-only and trend-following, it does not trade against the trend.
2. **Momentum confirmation:** 14-day RSI is between 50 and 70 (rising momentum, but excludes "already overbought" >70 to avoid chasing exhausted moves).
3. **Trigger:** a bullish crossover event in the last 1 trading day — specifically the 10-day EMA crosses above the 20-day SMA (a faster signal layered on the slower trend filter), confirming fresh upward momentum rather than a stale uptrend.

A ticker generates a **BUY signal** only when all three conditions hold simultaneously on the same engine run. This tightens the funnel deliberately — the engine is expected to trade selectively (a handful of signals per week across the whole watchlist), consistent with "daily trading and short-term swings," not high-frequency churn.

### 4.4 Position sizing

- Each BUY signal sizes a position at a fixed **% of the user's current `cash_balance`** — default **10% per position**, capped at a max of **5 concurrent open positions per user** (so at most ~50% of cash deployed at once if all 5 fire; remainder stays in cash as a risk buffer). Both numbers are config constants, not user-editable in MVP.
- If a BUY signal fires for a ticker the user already holds, it is skipped (no pyramiding/averaging up in MVP — simplest correct behavior).
- If a BUY signal fires but the user has reached the max concurrent positions, or has insufficient cash for even a partial position, the signal is skipped for that user on that run (not queued).
- Position size in shares = `floor((cash_balance * 0.10) / current_price)`. Fractional shares are not supported in MVP (matches typical free-tier broker-paper conventions and avoids extra precision complexity).

### 4.5 Exit logic (applies independently to every open position, checked every engine run)

Exit on **whichever of these triggers first**:
1. **Profit target:** price has risen ≥ 8% above entry price → sell (lock in swing gain).
2. **Stop loss:** price has fallen ≥ 4% below entry price → sell (cap downside; the 2:1 reward:risk ratio is a deliberate, simple convention for a swing strategy).
3. **Max holding period:** position has been held for **10 trading days** (≈2 calendar weeks) without hitting target or stop → sell at current price regardless of P&L. This directly enforces the "1–2 week holds" requirement as a hard ceiling, not a suggestion.
4. **Trend invalidation:** 20-day SMA crosses back below 50-day SMA → sell (the original trend thesis is broken, exit early even if neither target nor stop hit, and before max hold expires).

Whichever condition is met first on a given engine run closes the full position (no partial scale-outs in MVP — simplest correct behavior, consistent with no-pyramiding on entry).

### 4.6 Scheduling — how and when the engine runs

Given delayed daily data, real-time intraday ticks add no value and aren't supported. The engine runs as a **scheduled batch job, once per US trading day, after market close** (e.g. 17:00 US/Eastern, comfortably after the 16:00 ET close and after the data provider has settled the day's official OHLCV bar). Each run:

1. Fetches the latest daily bar for every ticker in the universe (Section 7).
2. Evaluates exit conditions first for every open position across every active user (so exits free up cash/slots before new entries are considered).
3. Evaluates entry conditions for the universe, then applies sizing/slot rules per active user.
4. Writes resulting trade records, updates account balances, and marks the run complete with a timestamp + summary (tickers evaluated, signals fired, trades executed, errors).

There is no on-demand/manual "run the engine now" trigger exposed to Regular Users. Admin gets a manual "trigger a run now" override in the admin panel for operational/debugging purposes only (e.g. to recover from a missed scheduled run) — this reuses the exact same engine code path, not a separate one.

Implementation note: a single shared **cron-style scheduler in the backend container** (e.g. APScheduler in the Python service) is sufficient for MVP local deployment — no separate job-queue infrastructure needed.

### 4.7 Determinism & shared application across users

The engine computes signals **once per run** (not once per user) since signals depend only on market data, not on any individual user's state. It then applies the resulting BUY/SELL decisions across every active user independently, respecting each user's own cash/position/slot constraints from Section 4.4. This guarantees the literal requirement: the same strategy, the same signals, applied identically to all users — while still respecting that two users with different cash balances will naturally end up with different share quantities and possibly different fills if processed at slightly different simulated times (see Section 5 on fill price).

---

## 5. Trade Execution & Logging

### 5.1 Simulated fill model

Because the data source is daily/delayed (Section 7), there is no real intraday tick to fill against. MVP fill convention: **all simulated entries and exits fill at the closing price of the daily bar that triggered the signal** (the same bar used to evaluate the signal). This is the standard, defensible convention for a daily-bar swing strategy and is explicitly stated so backtest and live engine math agree (Section 6 depends on this being the same fill rule in both modes).

This means a signal evaluated on Tuesday's close fills "as of" Tuesday's close — i.e. the engine run that happens after Tuesday's close (Section 4.6) books the trade dated Tuesday, executed retroactively to that bar's close. This is a known, accepted simplification of paper-trading systems using EOD data and is called out explicitly in Assumptions (Section 10) so it's never mistaken for true real-time execution.

No slippage or commission is modeled in MVP (flagged as an assumption — see Section 10) — fills are exact at the bar close price, zero transaction cost. This keeps the math simple and transparent for an MVP; it's a known idealization vs. real trading.

### 5.2 Trade record contents

Each row in the `trades` table contains:

| Field | Description |
|---|---|
| `id` | Unique trade id |
| `user_id` | Owning account |
| `ticker` | Symbol traded |
| `side` | `BUY` or `SELL` |
| `quantity` | Shares |
| `price` | Fill price (bar close, Section 5.1) |
| `trade_value` | `quantity * price` |
| `executed_at` | Timestamp of the engine run that booked it (and the bar date it corresponds to) |
| `signal_reason` | Which entry/exit rule fired (e.g. `ENTRY_TREND_MOMENTUM`, `EXIT_PROFIT_TARGET`, `EXIT_STOP_LOSS`, `EXIT_MAX_HOLD`, `EXIT_TREND_INVALIDATION`) — critical for explainability and for users/admin to understand *why* a trade happened |
| `realized_pnl` | Populated only on `SELL` rows — profit/loss for that closed round-trip, in dollars |
| `position_id` | Links the closing `SELL` back to the opening `BUY` (so a full round-trip is traceable) |
| `engine_run_id` | Links the trade to the specific scheduled run that produced it (for audit/debug) |

A logically separate `positions` table tracks currently **open** positions (user_id, ticker, quantity, entry_price, entry_date, entry_trade_id) so the engine doesn't need to re-derive open state by replaying the full trade log on every run. When a position closes, it's removed from `positions` and the full round-trip is captured by the matched BUY/SELL pair in `trades`.

### 5.3 Per-user trade history view

- Regular User: a "Trade History" page listing all their own trades (paginated, newest first), filterable by ticker and date range, each row showing side/ticker/qty/price/date/reason/realized P&L (where applicable). Also a "Current Positions" panel showing open holdings with live unrealized P&L (using the latest fetched price, recomputed at least once per engine run, not real-time intraday).
- Admin: same view, but selectable per-user (a user picker/search), plus an aggregate "all trades across all users" view for the current trading day (useful for spot-checking the engine's per-run behavior).
- All amounts displayed in USD, 2 decimal places, consistent with the underlying `DECIMAL(14,4)` storage (extra precision retained internally to avoid rounding error accumulation, display only rounds at render time).

---

## 6. Simulation / Backtest Feature (Admin)

### 6.1 Purpose

Lets Admin evaluate how the shared engine (Section 4) would have performed historically, independent of any real user account — this is a strategy-evaluation tool, not a per-user feature, and never touches real user balances or trade history.

### 6.2 Inputs

Admin submits a backtest request with:
- **Date range** (start date, end date) — must fall within the historical range available from the data provider (Section 7).
- **Tickers** — defaults to the full live-engine universe (Section 4.2), but Admin may narrow it to a subset for faster iteration/debugging.
- **Starting capital** — a virtual dollar amount (e.g. default $100,000) used purely for the backtest run, unrelated to any real account balance.
- (Implicitly fixed, not user-input for MVP: the strategy rules themselves — Section 4.3–4.5 — are not parameterized/tunable through the UI. The backtest tests the one shared strategy, it does not let admin try variants. Strategy tuning is a code change, not a UI feature, in MVP.)

### 6.3 Execution model

The backtest **reuses the exact same signal-evaluation and exit-rule code path as the live engine** (Section 4.7), run day-by-day over the historical OHLCV series for the selected tickers, using the same fill convention (bar close, Section 5.1), the same position sizing rule (10% per position, max 5 concurrent — Section 4.4), and a single simulated "virtual account" seeded with the starting capital. This is critical: it guarantees the backtest is actually testing the same logic that trades live, not a re-implementation that could silently drift out of sync.

Because the data source is daily bars (not tick data), the backtest is inherently a daily-bar simulation — fast to run (no need to replay intraday), and bounded by how much historical daily data the free API tier provides (Section 7).

### 6.4 Outputs

On completion, the backtest produces and stores a result record containing:
- **Equity curve**: total portfolio value (cash + mark-to-market positions) at the close of each trading day in the range — rendered as a line chart.
- **Total return** ($ and %) over the period.
- **Win rate**: % of closed round-trip trades that were profitable.
- **Total number of trades** (entries/exits/round-trips).
- **Max drawdown**: largest peak-to-trough decline in the equity curve, in % and $.
- **Average holding period** (days) across closed trades — sanity-checks that the engine is actually behaving as a 1–2 week swing strategy.
- **Per-trade log** for the backtest run (same shape as Section 5.2, scoped to this backtest, not commingled with any real user's `trades` table — stored in a separate `backtest_trades` table tied to a `backtest_run_id`).
- **Per-ticker breakdown** (optional nice-to-have, not blocking MVP): which tickers contributed most/least P&L.

### 6.5 Presentation

- Admin submits the backtest from a form (date range, tickers, starting capital) and the job runs synchronously if the range is short enough, or asynchronously (with a "running... check back" status) for longer ranges — given local Docker deployment and a free API's rate limits, a multi-year/multi-ticker backtest may take noticeable wall-clock time due to fetch throttling (Section 7), so the UI must support an async "queued → running → complete" status rather than blocking the request.
- Past backtest runs are listed (date run, parameters used, headline return/win-rate) so Admin can compare runs after a strategy code change over time.
- Results page shows the equity curve chart plus the summary metrics table plus an expandable trade log.

---

## 7. Market Data Integration

### 7.1 Source

**Primary: `yfinance`** (unofficial Yahoo Finance Python library) — free, no API key required, provides daily OHLCV history and recent quote data, sufficient for a daily/swing strategy. Chosen over Alpha Vantage as the default because Alpha Vantage's free tier has a stricter rate limit (5 requests/min, 500/day on older free keys, now even more restricted) and requires a registered API key, whereas yfinance has no key requirement and is simpler to operate locally. **Alpha Vantage is documented as a fallback/alternative** (config-swappable data provider interface) in case yfinance's unofficial endpoint becomes unreliable. This is recorded as an assumption (Section 10) since the user said "e.g. yfinance or Alpha Vantage" — yfinance is the concrete pick.

### 7.2 What's fetched

- **Daily OHLCV bars** (Open/High/Low/Close/Volume) per ticker in the universe — this is the core data the engine and backtest both run on (Section 4, 6).
- **Most recent quote/price** per ticker — used for live mark-to-market of open positions on the dashboard (Section 3.4, 5.3) between engine runs, understanding this is still delayed, not true real-time.
- Historical range needed for backtests is bounded by what yfinance returns for daily bars (commonly years of history for liquid large-caps — sufficient for MVP backtest ranges).

### 7.3 Caching & rate-limit handling

- A `market_data_cache` table stores fetched daily bars per ticker/date, written once when first fetched, never re-fetched for a date that's already cached (historical daily bars don't change once the trading day is over). This means repeated backtests over overlapping date ranges, or multiple engine runs needing the same recent bars, hit the local DB cache instead of re-hitting the external API — this is the primary defense against free-tier rate limits.
- The daily live engine run (Section 4.6) only needs **one new bar per ticker per day** — with a ~20–30 ticker universe, this is a small, predictable daily call volume well within yfinance's practical limits.
- Backtest requests over wide date ranges for tickers not yet cached will require bulk historical fetches; the client should request the full range in one call per ticker (yfinance supports ranged history in a single call — it does not require day-by-day requests), keeping call count to roughly one call per ticker per backtest, not one call per ticker per day.
- On fetch failure (network error, ticker delisted, provider hiccup) for a given ticker on a given run: log the error, skip that ticker for that run (do not crash the whole engine run), and surface a clear error/warning in the admin's "engine run" log/status view (Section 4.6 run summary). The 3d70555 pattern already established in a sibling project in this workspace — "fall back gracefully instead of crashing" — is the right precedent to follow here too.
- No paid upgrade path is in scope for MVP; if rate limits become a real operational problem, the fix is reducing universe size or fetch frequency, not adding a paid tier (that would be a deliberate v2+ decision).

---

## 8. Functional Requirements (User Stories & Acceptance Criteria)

### 8.1 Admin stories

**FR-1: Bootstrap the first Admin account**
As an operator, I need a working Admin login on first deployment without any pre-existing user.
- AC1: On first backend startup with `ADMIN_BOOTSTRAP_EMAIL`/`ADMIN_BOOTSTRAP_PASSWORD` set in `.env`, exactly one Admin user exists in the DB after startup.
- AC2: Restarting the backend again does not create a duplicate or second seeded admin.
- AC3: If the env vars are missing and no admin exists yet, the backend logs a warning and the system has no usable login (documented, expected behavior, not a silent failure).

**FR-2: Create a user**
As an Admin, I can create a new Regular User or Admin account.
- AC1: Submitting a unique email, display name, password, and role creates a new active user with a `$0.00` account.
- AC2: Submitting a duplicate email is rejected with a clear error and no user is created.
- AC3: The new user can immediately log in with the credentials set.

**FR-3: Delete (deactivate) a user**
As an Admin, I can remove a user's access.
- AC1: Deactivating a user sets `is_active = false`; that user can no longer log in (correct credentials are rejected with an "account disabled" style message, not a generic auth failure that implies wrong password).
- AC2: The user's historical trades remain visible to Admin after deactivation.
- AC3: The engine does not evaluate or act on a deactivated user's account on subsequent runs; any open position they held stops updating (per Section 3.2 default).

**FR-4: Fund a user's account**
As an Admin, I can load virtual cash into any active user's account.
- AC1: Submitting a positive dollar amount increases that user's `cash_balance` by exactly that amount and creates a `fund_transactions` record.
- AC2: Submitting a zero or negative amount is rejected with a validation error.
- AC3: A user whose `cash_balance` moves from `$0` to `>$0` is included in the very next scheduled engine run's eligible universe of accounts.

**FR-5: View any user's trade history and balances**
As an Admin, I can inspect any user's account.
- AC1: Selecting a user shows their current balance breakdown (cash/equity/total), open positions, and full trade history with the same fields as Section 5.2.
- AC2: This view works identically for active and deactivated users (read access is not blocked by deactivation, only login is).

**FR-6: Trigger an engine run manually**
As an Admin, I can force an engine run outside the schedule for operational recovery.
- AC1: Triggering a manual run executes the identical code path as the scheduled run (Section 4.6, 4.7) and produces the same kind of `engine_run` summary record.
- AC2: Manual trigger is rejected with a clear message if a run is already in progress (no overlapping runs).

**FR-7: Run a backtest**
As an Admin, I can evaluate the strategy against historical data.
- AC1: Submitting a valid date range, optional ticker subset, and starting capital produces a backtest result containing equity curve, total return, win rate, trade count, max drawdown, and average holding period (Section 6.4).
- AC2: Submitting an end date before the start date, or a date range outside available historical data, is rejected with a clear validation error before any compute starts.
- AC3: Backtest results are persisted and listed under a history of past runs, each independently viewable.
- AC4: Running a backtest never modifies any real user's account, balance, or trade history.

### 8.2 Regular User stories

**FR-8: Log in**
As a Regular User, I can log in with credentials given to me by an Admin.
- AC1: Correct email + password returns a valid access/refresh token pair and routes me to my dashboard.
- AC2: Incorrect credentials are rejected without revealing whether the email exists (generic "invalid email or password" message).
- AC3: A deactivated account is rejected even with correct credentials, with a distinct "account disabled, contact your admin" message.

**FR-9: View my account balance**
As a Regular User, I can see my current cash, equity, and total value.
- AC1: Dashboard shows `cash_balance`, `equity_value` (mark-to-market, updated at least as of the most recent engine run), `total_value`, lifetime `realized_pnl`, and current `unrealized_pnl`.
- AC2: A user with `$0` balance sees a clear zero-state explaining they are not yet funded/active (not a blank/broken-looking page).

**FR-10: View my open positions**
As a Regular User, I can see what I currently hold.
- AC1: Each open position shows ticker, quantity, entry price, entry date, days held so far, current price, and unrealized P&L ($ and %).

**FR-11: View my trade history**
As a Regular User, I can see every trade ever executed on my account.
- AC1: A paginated, newest-first list of all trades (Section 5.2 fields), filterable by ticker and date range.
- AC2: Each closed round-trip trade clearly shows realized P&L and the exit reason (target/stop/max-hold/trend-invalidation).
- AC3: I cannot see any other user's trades or balances (enforced server-side via token-derived user_id, not just hidden in the UI).

### 8.3 Cross-cutting

**FR-12: Role-based access enforcement**
As the system, I must prevent privilege escalation and cross-account data leaks.
- AC1: Every `/admin/*` API route returns `403 Forbidden` for a valid token with `role == user`.
- AC2: Every "my data" route derives the user scope strictly from the authenticated token's `user_id`, ignoring any user_id present in the request body/query string.
- AC3: Expired access tokens return `401 Unauthorized`; the frontend transparently uses the refresh token to retry once before forcing re-login.

---

## 9. Non-Functional Requirements

### 9.1 Security basics
- Passwords hashed (bcrypt/argon2), never logged or returned in any API response.
- JWT signing secret loaded from `.env`, never hardcoded or committed.
- All admin-only routes enforce RBAC server-side (Section 2.2, FR-12) — never rely on the frontend hiding a button as the only protection.
- Input validation on all write endpoints (fund amount > 0, email format, date ranges, etc.) — reject bad input with 4xx before touching the DB.
- Rate-limit/login-throttle on the login endpoint to blunt brute-force attempts (e.g. basic per-IP or per-email lockout after repeated failures) — lightweight for MVP, not a full WAF.
- No secrets (API keys, DB credentials, JWT secret) committed to the repo — `.env` stays gitignored (already true per existing `.gitignore`).

### 9.2 Data persistence
- Relational DB (Postgres recommended, consistent with `DECIMAL` precision needs in Section 3.4) running as its own Docker Compose service, with a named volume so data survives container restarts/rebuilds.
- Daily backup is out of scope for local MVP (single-operator local deployment, not production-critical data) — flagged as an assumption, not a gap to silently ignore.
- Market data cache (Section 7.3) persists in the same DB so restarting containers doesn't force a full historical re-fetch.

### 9.3 Performance expectations (given delayed data)
- The system is explicitly **not** designed for low-latency or real-time responsiveness in trading decisions — once-daily engine runs are the expected cadence, and this is a feature of the design, not a limitation to optimize away.
- API response times for dashboard/history views: target <1s for typical per-user data volumes (hundreds to low-thousands of trade rows per user) on local hardware — no special caching/indexing beyond standard DB indexes on `user_id`/`ticker`/`executed_at` is needed at MVP scale.
- A single scheduled engine run across a ~20–30 ticker universe and a modest user count (tens of users, not thousands) is expected to complete well within minutes, bounded mainly by external API fetch latency, not compute.
- Backtests over multi-year ranges may take longer (data-fetch-bound on first run, fast on cached re-runs per Section 7.3) — async status reporting (Section 6.5) absorbs this rather than requiring sub-second backtest turnaround.
- No defined SLA/uptime target — this is a local Docker Compose tool for a small number of users, not a hosted service with external users depending on availability.

### 9.4 Observability
- Each engine run produces a persisted summary record (Section 4.6) — tickers evaluated, signals fired, trades executed, errors encountered — viewable by Admin. This is the primary debugging surface for "did the engine behave correctly today."
- Structured backend logging (info/warn/error) to stdout, captured by Docker Compose logs (`./run.sh logs`), consistent with existing project conventions.

---

## 10. Assumptions & Open Decisions

These are decisions made to keep the MVP buildable without re-opening locked requirements. Each is a reasonable default, not a question for the stakeholder — but they're listed explicitly so they can be revisited deliberately in a later version if needed.

1. **Tech stack**: Python backend + React frontend + Docker Compose, per the existing repo scaffold (`api/`, `frontend/`, `docker-compose.yml` already present). Postgres assumed as the DB (not specified in scaffold yet) for `DECIMAL` precision and reliability; SQLite would be simpler but riskier for concurrent engine-write + API-read access patterns even at small scale.
2. **Strategy parameters** (20/50-day SMA trend filter, 14-day RSI 50–70 band, 10-day EMA crossover trigger, 10%-per-position sizing, 5-position cap, 8% target / 4% stop / 10-trading-day max hold, trend-invalidation exit) are concrete starting values chosen to satisfy "daily trading and short-term swings (1–2 week holds)" with a simple, explainable, long-only trend/momentum approach. These are config constants, not hardcoded magic numbers buried in logic, so they can be tuned later without a rewrite — but tuning itself is out of scope for MVP UI.
3. **Fixed watchlist universe** (~20–30 liquid large-cap US tickers + 1–2 broad ETFs) rather than scanning the full market, to respect free-tier API rate limits and keep MVP scope bounded. The exact ticker list is a backend config decision at implementation time, not specified here.
4. **No fractional shares, no margin, no short selling** — simplest correct long-only model consistent with "paper trading," not stated explicitly in the locked requirements but a reasonable reading of "paper-trading platform for US stocks" without further qualification.
5. **No slippage/commission modeling** — fills are exact at bar-close price (Section 5.1) with zero transaction cost. A known idealization; flagged so it's never mistaken for realistic execution modeling.
6. **Soft-delete (deactivate) instead of hard-delete for "delete user"** — preserves trade-history integrity and avoids orphaned foreign keys. The locked requirement says "delete users" but doesn't specify whether historical data must be erased; soft-delete is the safer, more standard interpretation and is reversible if wrong.
7. **Deleted/deactivated users' open positions are left untouched (not auto-liquidated)** by the engine — they simply stop being processed. An alternative (auto-close positions on deactivation) is equally defensible; this PRD picks "do nothing automatically" as the safer default since silent liquidation could surprise an admin. Revisit if real usage shows otherwise.
8. **Whether the last remaining Admin can delete themselves, or delete the only other Admin** is left unresolved at the requirements level — implementation should block deleting the last active Admin account to avoid a total lockout, but this wasn't explicitly specified and is called out here rather than silently decided in code.
9. **Funding is additive-only** (no "withdraw" or "set balance" admin action) — simplest model satisfying "load virtual funds into user accounts." If real usage needs balance correction/clawback, that's a v1.1 addition, not assumed here.
10. **yfinance chosen as the concrete data source** over Alpha Vantage (the locked requirement named both as examples) — based on no-API-key requirement and looser practical rate limits for a ~20–30 ticker daily universe. Data provider is implemented behind an interface so swapping to Alpha Vantage later is a config/adapter change, not a rewrite.
11. **No email/SMS infrastructure** — password reset is admin-mediated (Section 2.2) rather than email-link-based, to avoid requiring an email provider dependency for a local MVP tool.
12. **No backups/DR plan** for the local Docker Compose deployment — acceptable for a local single-operator MVP; would need revisiting before any future cloud phase (explicitly out of scope per Section 1.4, consistent with the project's general pattern of "v1 local Docker Compose, cloud later").
13. **Admin watchlist editing** (whether Admin can add/remove tickers from the universe via UI vs. it being a static backend config) is left as a backend config file for MVP — not exposed in the admin UI. This can be promoted to an admin-editable setting in a later iteration without architectural rework.
14. **Backtest admin-only, fully isolated from live data** — backtests never write to the real `trades`/`positions`/`accounts` tables, only to dedicated `backtest_runs`/`backtest_trades` tables, so there's no risk of contaminating real user history with simulated test runs.
15. **Multi-admin model is flat** (no admin-tiering) — any admin can do anything any other admin can, including funding/deleting accounts created by a different admin. Simpler permission model, consistent with no locked requirement suggesting tiered admin permissions.
