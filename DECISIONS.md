# Decisions — Backend foundation slice (feature/mvp-iteration-1)

Decisions made while implementing the backend-foundation slice where the
architecture/PRD were silent on exact mechanics, or where a library
incompatibility forced a choice. Each is reasonable and reversible.

1. **Case-insensitive unique email via a generated `email_lower` column**,
   not Postgres's `citext` extension. Architecture 3.2 says "CITEXT/TEXT
   UNIQUE; case-insensitive unique" — `citext` would require enabling the
   extension in the migration (`CREATE EXTENSION citext`), an extra
   operational step for a single-operator local deployment. Storing
   `email.lower()` in a second column with a plain unique constraint
   gets the same guarantee with zero extra DB setup. `email` keeps the
   user's original casing for display; `email_lower` is write-once,
   derived at insert time by application code (not a DB trigger, kept
   simple for MVP).

2. **`role`/`side`/`status`/`signal_reason`/`trigger` are TEXT + CHECK
   constraint**, not native Postgres ENUM types. Adding a new allowed
   value later is an `ALTER TABLE ... DROP CONSTRAINT / ADD CONSTRAINT`
   (or even a code-only relaxation), not a `ALTER TYPE` migration with
   its own quirks. Equivalent data integrity, simpler evolution.

3. **`trades.position_id` has no FK constraint to `positions.id`.**
   Architecture 3.2 states positions are deleted when a position closes,
   while the matching SELL `trades` row must persist forever (append-only
   log). A hard FK would either block the position delete or require
   `ON DELETE SET NULL`/cascade semantics not specified anywhere in the
   docs. Left as a plain `BIGINT NULL` column — the link is still queryable
   by joining trades to historical position ids if ever needed, but the
   DB doesn't enforce referential integrity here, mirroring the lifecycle
   mismatch between the two tables.

4. **`bcrypt` pinned to `4.0.1`, not the latest 4.2.x.** `passlib==1.7.4`'s
   bcrypt backend probes `bcrypt.__about__.__version__` at first
   hash/verify call; that attribute was removed in `bcrypt>=4.1`, causing
   a crash. Verified locally that `4.0.1` works correctly with
   `passlib[bcrypt]==1.7.4`. This is a known upstream incompatibility
   (passlib has not cut a new release fixing this as of this writing).

5. **Hand-wrote the initial Alembic migration** instead of running
   `alembic revision --autogenerate`, since no live Postgres is available
   in this build environment. Verified correctness by compiling
   `CreateTable()` for every ORM model against the `postgresql` dialect
   and diffing column-by-column against `app/models.py` and architecture
   3.2's table sketches. The migration should be re-verified with a real
   `alembic upgrade head` against a live `db` service the first time
   `docker compose up` runs end-to-end.

6. **Indexes added on `trades`**: `(user_id, executed_at)`,
   `(user_id, ticker)`, `(engine_run_id)` — architecture 3.2 calls these
   out by name ("Indexes: ... for the newest-first history view ... for
   the ticker filter ... for the admin 'trades today' view") but they
   aren't shown in the architecture's hand-drawn DDL sketch, so they were
   added explicitly in the migration since the doc clearly intends them.

7. **Test suite uses an in-memory sqlite subset of the schema**, omitting
   `engine_runs` and `backtest_runs` (the two tables with Postgres-only
   `JSONB` columns) since this slice's tests don't exercise engine or
   backtest logic. `BigInteger` autoincrement PKs are coerced to
   `Integer` only inside the sqlite test fixture (via a `before_create`
   DDL event) so sqlite's native rowid autoincrement applies — this has
   no effect on the real Postgres schema, which uses `BIGSERIAL`
   regardless, independently verified via dialect-targeted DDL
   compilation in `test_models.py`.

8. **`app/strategy_config.py` is a plain Python module of constants**,
   separate from `app/config.py` (the pydantic-settings env-driven
   config). Strategy parameters and the universe are fixed, non-secret,
   non-environment-specific values (architecture assumption 11 / PRD
   assumption 13: not admin-editable, not env-driven) — module constants
   are simpler than wiring them through `BaseSettings` for no benefit.

9. **Universe list**: chose 26 tickers (24 large-cap S&P 500 names +
   SPY + QQQ) as a concrete instantiation of "the exact ticker list is a
   backend config decision at implementation time, not specified here"
   (PRD assumption 3). Liquid, well-known large caps across sectors;
   swappable later without any schema change since it's pure config.

# Decisions — Auth + RBAC slice (feature/mvp-iteration-1)

10. **Login schema uses plain `str` for email, not Pydantic's
    `EmailStr`.** `EmailStr` requires the optional `email-validator`
    package, which is not in `requirements.txt` and wasn't added since
    the task scope said "keep it minimal." Malformed emails simply fail
    the DB lookup and fall through to the same generic 401 as an unknown
    email — this is actually *more* consistent with architecture 9.1's
    account-enumeration resistance than a 400 would be, since a 400
    would let an attacker distinguish "malformed" from "well-formed but
    wrong" without even reaching the throttle.

11. **Refresh token carries only `sub` (user_id), not `role`.** On
    `/auth/refresh`, role is re-read from the DB rather than trusted from
    the refresh token's claims, so an admin who gets demoted to `user`
    (or deactivated) takes effect on their very next refresh instead of
    silently keeping `admin` in their access token for up to 7 days.

12. **`require_auth` rejects inactive users with 401, not 403.**
    Architecture 6.2 says `require_auth` "rejects expired (401) and
    inactive users" without specifying the inactive-user status code for
    *already-issued* tokens. 403 "Account disabled" is explicitly the
    `/auth/login` response per architecture 5.1/9.1; reusing 401 here
    means a deactivated user's still-valid access token just looks like
    "not authenticated" rather than leaking account-state detail on every
    subsequent API call.

13. **Login throttle keys on (IP, email) independently** — locking either
    key blocks the attempt. A high-volume attacker rotating emails from
    one IP is stopped by the IP key; credential-stuffing one email from
    rotating IPs is stopped by the email key. Per architecture 6.4 /
    assumption 6, this is intentionally simple (module-level dict, no
    persistence, resets on restart).

14. **Refresh cookie `Secure` flag is hardcoded `False`.** Per
    architecture 9.2 ("No HTTPS locally") and the task's explicit
    instruction ("Secure off for local"), there's no env-driven
    prod/local switch in this slice — flagged in `app/routers/auth.py`
    as something to revisit before any non-local deployment.

15. **`app/deps.py` re-exports `app.db.get_db`** rather than defining a
    second DB session dependency, even though the task description asked
    for "a DB session dependency too" in `deps.py`. The existing
    `app.db.get_db` (slice 1) already does exactly this; importing and
    re-exporting it avoids two near-identical session-management
    functions that could drift, while still letting routers
    `from app.deps import get_db` alongside the auth dependencies.

# Decisions — Admin user + fund management slice (feature/mvp-iteration-1)

16. **A global `RequestValidationError` -> 400 handler was added in
    `app/main.py`**, instead of leaving FastAPI's default 422 for bad
    Pydantic input. Architecture 5/9.1 and PRD FR-2/FR-4 ACs explicitly
    say "400" for weak password, malformed email, and `amount <= 0` —
    422 would silently violate the documented contract. The handler
    reuses the same `{"detail": "<message>"}` error shape as every other
    error response (architecture 5 conventions) by taking the first
    Pydantic error message. This applies API-wide (not just to
    `/admin/users`), which is intentional: every other write endpoint in
    this codebase should get the same documented 400 behavior, not a
    one-off carve-out for this router.

17. **Admin user creation validates email with the same minimal regex as
    `app/schemas/auth.py`'s comment describes**, not `EmailStr` (still
    not in `requirements.txt`). Unlike login, this *does* return 400 on
    a malformed email (via the validator raising `ValueError`) since
    `POST /admin/users` is not a public/unauthenticated endpoint — there
    is no account-enumeration concern to preserve here, only the FR-2
    AC2-adjacent "bad email -> 400" requirement (architecture 5.2).

18. **Password minimum length is 8 characters**, chosen as "a reasonable
    minimum" per the task's "(e.g. >=8)" suggestion. Not specified more
    precisely anywhere in the PRD/architecture.

19. **`GET /admin/users` search (`q`) matches against `display_name`
    (case-insensitive) OR `email_lower`**, substring/contains match. The
    architecture's query-param sketch (`q=`) doesn't specify which
    field(s) it searches; matching both display name and email is the
    most useful interpretation for an admin trying to find a user by
    either piece of identifying info they might have on hand.

20. **`list_users`'s `status` query param is bound via
    `Query(alias="status")`** onto a Python parameter named
    `status_filter` (avoiding shadowing the `status` module imported from
    `fastapi` in the same file). Caught by a test that asserted status
    filtering actually narrowed results — without the alias, FastAPI
    silently never populates the filter from `?status=...` and the route
    quietly returns all users regardless of the requested status.

21. **`POST /admin/users/{id}/fund` lazily creates the user's `Account`
    row if one is somehow missing**, rather than 404/500ing. Every user
    created via `POST /admin/users` already gets a 1:1 account, so this
    only matters for data that predates this invariant; treated as a
    defensive no-op rather than a real expected code path.

22. **The last-admin guard only runs when the target user is currently
    `is_active=true` AND `role='admin'`** — deactivating an already-
    inactive admin, or a non-admin user, never triggers the active-admin
    count query. This matches the literal requirement ("block
    deactivating the final active admin") without adding an unnecessary
    DB round-trip for the common case (deactivating a regular user).

23. **No "edit user" or "reset password" endpoint was added** in this
    slice — out of scope per the task's explicit instruction list
    ("Admin user + fund management" only); PRD 2.2 mentions admin-
    mediated password reset as a future/already-decided capability but
    it wasn't named in this slice's 5 required endpoints, so it's left
    for a later slice.

# Decisions — Market data adapter + trading engine slice (feature/mvp-iteration-1)

24. **`get_daily_bars()`'s "cache covers the request" check uses a
    4-calendar-day tolerance**, not an exact match on `as_of`. Architecture
    7.2 says cache hits read straight from `market_data_cache` and misses
    fetch+write, but doesn't specify how to detect "do we already have
    the bar for today" when `as_of` itself might be a weekend/holiday
    with no bar. A tolerance window (most recent cached row within 4
    days of `as_of`) avoids re-fetching every single run just because
    today has no bar yet, while still re-fetching when the cache is
    genuinely stale (e.g. first run after a long gap). Once any date is
    cached it is never overwritten or re-fetched individually — only the
    decision "is a fetch needed at all" uses this tolerance.

25. **`MarketDataProvider._fetch` is the sole network-touching method**,
    deliberately separated from `get_daily_bars()`'s cache logic, so
    tests (and the engine runner / scheduler) can inject a fake provider
    instance and never hit yfinance. `app/engine/runner.py` and
    `app/scheduler.py` both thread an optional `provider` parameter
    through to `get_daily_bars()` for exactly this reason — production
    code paths never pass one (falling back to `YFinanceProvider`), only
    tests do.

26. **Alpha Vantage fallback is a stub that raises `NotImplementedError`**,
    per the task's explicit instruction. Its class shape (subclassing
    `MarketDataProvider`, implementing `_fetch`) exists so a future slice
    can fill in the real HTTP call without touching `get_daily_bars()` or
    any caller.

27. **Crossover detection (`EMA10 crosses above SMA20`, `SMA20 crosses
    below SMA50`) is implemented as a strict edge check** (`prev_a <=
    prev_b and a > b`), not "is currently above/below." This matches the
    PRD's literal "crosses" language for both the entry trigger and the
    trend-invalidation exit, and keeps entry/exit logic symmetric. A
    consequence: if a ticker's data has a gap (e.g. a skipped engine run)
    spanning the actual crossover bar, the edge is missed and won't
    re-fire later — accepted as a known edge case of using bar-to-bar
    edge detection with a daily-batch design; not addressed in this
    slice.

28. **`check_exit()` takes `trading_days_held` as a caller-supplied int**
    rather than computing it from dates internally. The engine runner
    computes this by counting cached daily bars strictly after
    `entry_date` through `as_of_date` (trading days, not calendar days,
    per PRD 4.5.3 "10 trading days"). Keeping this out of `signals.py`
    keeps that module a pure function of indicator values with no DB
    access, so the future backtest path (which iterates bar-by-bar and
    can track a simple running counter instead of querying the cache
    every day) can supply the count however is cheapest for its own loop.

29. **`run_engine()`'s signal-layer market-data commit is separate from
    each account's apply-layer transaction.** Newly-fetched
    `market_data_cache` rows are committed once, immediately after the
    signal layer runs, before any account is touched — architecture 4.4
    says "all of (1)-(4) for a single account happen in ONE DB
    transaction," which is about per-account trade/position/cash
    mutations, not the shared, account-independent market-data cache
    writes. Committing the cache early also means a fetch that succeeded
    is never lost even if a later account's transaction has to roll back.

30. **A failed per-account transaction is caught, rolled back, and
    recorded in `errors`, but does not fail the whole run** — the run's
    overall `status` still becomes `'complete'` as long as the signal
    layer itself didn't raise. This follows architecture 7.2's closing
    paragraph ("already-committed per-account transactions stand... the
    run is resumable/auditable rather than all-or-nothing") and PRD
    7.3's "a single bad ticker does not fail the run," extended by
    analogy to "a single bad account does not fail the run" since no
    other account's correctness depends on it.

31. **Single-flight uses the `engine_runs` status='running' row as the
    primary, portable check, with the Postgres advisory lock as a
    secondary belt-and-suspenders guard** that is a deliberate no-op on
    non-Postgres dialects (detected via `db.get_bind().dialect.name`).
    This matches architecture 3.2's own framing ("a single status='running'
    row + a Postgres advisory lock is the single-flight mechanism") and
    lets the single-flight test suite run against sqlite without any
    Postgres-specific test infrastructure, while the advisory lock still
    provides real cross-process protection in the deployed Postgres
    environment.

32. **The scheduler-start guard checks `"pytest" in sys.modules`**, not
    only `settings.enable_scheduler`. The task said "guard so it doesn't
    start during tests / import — e.g. only start when not under pytest,
    or behind a settings flag" (an explicit "or"); the pytest-module
    check is the more foolproof default for this codebase's actual test
    setup (TestClient runs the real `lifespan`), since it requires zero
    test-fixture coordination to stay correct, while
    `settings.enable_scheduler` remains available as a manual override
    for local debugging (e.g. running uvicorn directly without wanting
    the cron to fire).

33. **`misfire_grace_time=None`** on the daily cron job, meaning a missed
    17:00 ET firing (e.g. container was down) is simply skipped, not
    caught up later. PRD 4.6 explicitly names the admin manual-trigger
    button as the documented recovery path for a missed scheduled run,
    so no catch-up logic was added.

34. **`tests/conftest.py` gained a second sqlite fixture
    (`db_session_with_engine_runs`)** rather than adding `engine_runs` to
    the existing `SQLITE_SAFE_TABLES`/`db_session` fixture outright. The
    existing fixture's tests (auth, admin) never touch `engine_runs` and
    its real column is Postgres JSONB; introducing a second, additive
    fixture for this slice's tests avoids any risk of changing behavior
    for already-passing test modules from prior slices.

# Decisions — Engine control + portfolio + trade-history slice (feature/mvp-iteration-1)

35. **`GET /admin/engine/status`'s `next_scheduled_run` is computed
    independently** from `strategy_config.ENGINE_SCHEDULE_HOUR/MINUTE/
    TIMEZONE` via `zoneinfo`, not read off the live APScheduler job
    object. The architecture's design 4.10 just says the field is shown
    on the polled status screen; there's no existing helper that exposes
    APScheduler's own `next_run_time` to a request handler (the
    scheduler instance lives in `app.main`'s lifespan closure, not a
    module-level singleton), and the test suite never starts a real
    scheduler (architecture 2.4's pytest guard). A pure projection off
    the same config constants APScheduler itself uses is simpler and
    gives an identical answer in practice.

36. **`/admin/trades-today` defines "today" as the trades belonging to
    the single most-recently-started `engine_runs` row**, not literally
    `WHERE bar_date = today's calendar date`. Architecture 5.4 / design
    4.9 name the view but don't define "today" precisely, and the
    engine's `bar_date` can legitimately lag the wall-clock date (e.g.
    Friday's bar gets booked by the run that fires Friday evening, but a
    Saturday/Sunday page view still wants to see "the last run's
    trades," not an empty result because no bar exists for today).
    Scoping by `engine_run_id == most-recent-run.id` is the more useful
    reading and degrades gracefully (empty feed, zeroed summary) before
    any run has ever happened.

37. **`signals_skipped` in the `/admin/trades-today` summary is
    approximated as `max(signals_fired - trades_executed_today, 0)`**,
    since `engine_runs` (architecture 3.2) has no column that directly
    counts per-user skipped signals (slot-cap/dup-ticker/insufficient-
    cash skips happen inside the per-account apply loop and aren't
    individually persisted). This is a reasonable summary-level proxy,
    not an exact count of skip reasons; flagged here since the design
    doc's `{trades, users_evaluated, signals_skipped, errors}` shape is
    specified but its exact derivation isn't.

38. **`/me/positions`' `days_held` is calendar days** (`today -
    entry_date`), not the trading-day count the engine's own max-hold
    exit rule uses internally (`app/engine/runner.py`'s
    `_trading_days_held`, which counts cached bars). FR-10 AC1 just says
    "days held so far" with no trading-calendar requirement, and a
    calendar-day count is simpler to compute on every page load without
    re-querying `market_data_cache` per position. The two numbers can
    differ by weekends/holidays; this is a deliberate simplification for
    the display-only field, noted in a comment at the call site too.

39. **All money-shaped fields in `app/routers/portfolio.py` (including
    the dimensionless `unrealized_pnl_pct`) are explicitly quantized to
    4 decimal places** before being rendered as strings (`_money_str`),
    rather than relying on whatever precision a particular Decimal
    arithmetic expression happens to produce. Without this, e.g.
    `Decimal("0") + ...` or a percentage division can come back as
    `"0"` or `"10.0"` instead of `"0.0000"`/`"10.0000"`, which is
    inconsistent with every DECIMAL(14,4) column's natural string form
    elsewhere in the API (e.g. `admin_users.py`'s fund endpoints) and
    was caught by a zero-state test asserting the exact string shape.

40. **`POST /admin/engine/run`'s 202 response and the 409 conflict path
    both go through the unmodified `app.scheduler.trigger_manual_run`**
    — the router adds no new single-flight logic of its own, only an
    `except EngineRunInProgress -> HTTPException(409)` translation, per
    the existing module's own docstring note ("the next slice's
    POST /admin/engine/run route wraps trigger_manual_run directly").

41. **`GET /admin/users/{id}/trades` and `GET /me/trades` share one
    internal `_query_trades()` helper** parameterized by `user_id`,
    rather than duplicating the filter/paginate/order logic. The admin
    route's `user_id` comes from the path (already validated against a
    404 check); `/me/trades`'s comes from the auth-derived `user.id` —
    the helper itself is agnostic to where its `user_id` argument came
    from, so there's no risk of the shared code accidentally trusting a
    client-supplied value.

42. **No new `Account`/`Position`/`Trade` indexes were added** beyond
    what slice 1's migration already created (`(user_id, executed_at)`,
    `(user_id, ticker)` on `trades`, per DECISIONS.md item 6) — this
    slice's queries (`/me/trades`, `/admin/users/{id}/trades`,
    `/admin/trades-today`) all filter on columns already covered by
    those indexes or by `engine_run_id` (also indexed per item 6), so no
    schema/migration change was needed.

## Decisions — Backtest slice (feature/mvp-iteration-1)

43. **The virtual account in `app/engine/backtest.py` is a plain
    dataclass (`VirtualAccount`/`VirtualPosition`), not an ORM row.**
    Architecture 4.6 says the backtest "seeds a single in-memory virtual
    account with `starting_capital`," which only makes sense as a
    non-persisted object — there is no `accounts`-shaped table for
    backtests, by design (isolation, assumption 14). The apply-layer
    functions in `app/engine/backtest.py` mirror
    `app/engine/runner.py`'s `_process_exits`/`_process_entries`
    signatures and exact sizing/exit math, but operate on this plain
    object instead of a `Session`-backed `Account`/`Position`, since
    there is nothing to commit per-account (only `BacktestTrade` rows
    are persisted).

44. **The backtest's trading-day calendar is the union of bar dates
    across all requested tickers within `[start_date, end_date]`**, not
    a fixed market calendar. The PRD only specifies "day-by-day over the
    historical OHLCV series" (6.3) without defining the canonical
    trading-calendar source; using the actual cached bar dates avoids
    needing a separate holiday/weekend calendar dependency and
    naturally matches whatever the data provider actually returned for
    that ticker (handles newly-listed tickers, gaps, etc. the same way
    the live engine's cache-first reads already do).

45. **Per-ticker history for a backtest is fetched once for the whole
    `[start_date - lookback, end_date]` window**, not once per simulated
    day. This matches PRD 7.3's "bulk-fetched once per ticker per run"
    requirement and architecture 4.6's "bulk-fetched once per ticker per
    run" phrasing — `get_daily_bars()` is called once per ticker with a
    lookback wide enough to cover the whole requested range, and each
    simulated day takes a prefix slice of that already-fetched list
    in-memory (`compute_indicator_set` is then called once per
    ticker/day on that slice, unmodified from the live engine's version).

46. **`avg_holding_days` is computed via a FIFO queue of BUY bar-dates
    per ticker**, matched against SELL trades in execution order. The
    PRD doesn't specify how to pair entries with exits when computing
    "average holding period," but since the strategy enforces "no
    pyramiding" (one open position per ticker at a time, both live and
    in the backtest's own sizing logic), a simple FIFO match per ticker
    is unambiguous and correct — there is never more than one open BUY
    per ticker to match against a given SELL.

47. **`POST /admin/backtests` uses FastAPI `BackgroundTasks`**, not a
    second APScheduler job. Architecture 2.4 explicitly allows either
    ("APScheduler's thread pool / FastAPI `BackgroundTasks`") and notes
    "a `backtest_run` row is the queue" — `BackgroundTasks` needs no
    extra wiring beyond what FastAPI already provides per-request, and
    the `backtest_runs.status` column (queued/running/complete/failed)
    is itself the only state a client needs to poll, matching PRD 6.5's
    "queued → running → complete" UX without adding a second scheduler
    instance (which would also conflict with architecture 8.2's
    single-Uvicorn-process scheduler caveat for an unrelated reason).

48. **`validate_date_range()`'s "out of provider range" check only
    rejects a request when the cache already has data for the requested
    tickers and the requested range falls completely outside it**; if
    nothing is cached yet for those tickers (cold cache, e.g. a never-
    before-backtested ticker), the request is allowed through rather
    than rejected. PRD FR-7 AC2 says reject "out of provider range," but
    the provider's true historical range isn't knowable without an
    actual network fetch (which the validation step deliberately avoids
    triggering, to keep `POST /admin/backtests`'s 202 response fast) —
    a cold cache is therefore treated as "unknown range, let the run
    itself discover and report whether ticker data exists" rather than
    a hard validation failure.

49. **Tests for `app/engine/backtest.py` and `/admin/backtests*` add
    sqlite-backed `db_session_with_backtest_runs` /
    `client_with_backtest_runs` fixtures to `tests/conftest.py`**,
    mirroring the existing `*_with_engine_runs` fixture pair exactly
    (same JSONB→JSON sqlite coercion pattern, applied to
    `backtest_runs`' two JSONB columns: `tickers` and `equity_curve`).
    No existing fixture was modified beyond the shared
    `SQLITE_SAFE_TABLES`/`_PK_TABLES` list additions needed for the new
    table.

# Decisions — Frontend slice (feature/mvp-iteration-1)

50. **API base URL defaults to an empty string (relative paths) and the
    frontend relies on CRA's dev-server `proxy` field** (`"proxy":
    "http://api:8000"` in `frontend/package.json`), rather than setting
    `REACT_APP_API_BASE` to an absolute `http://localhost:8000`. The
    backend has no CORS middleware configured (confirmed by inspection
    of `api/app/main.py` — no `CORSMiddleware`), and the refresh token is
    an HttpOnly cookie (architecture 6.1) that must stay first-party to
    be sent automatically. Architecture 8.1 explicitly offers "CRA dev
    proxy (CRA `proxy` field) or an explicit `REACT_APP_API_BASE`" as
    alternatives — the proxy keeps the browser on a single origin
    (`localhost:3000`) with zero backend changes, which is in-scope for
    this frontend-only slice; an absolute `REACT_APP_API_BASE` would
    require adding CORS + cookie `SameSite`/cross-site handling to the
    FastAPI app, which is backend work explicitly out of scope here.
    `REACT_APP_API_BASE` is still read by `src/api/client.js` and can be
    set to override this if a future slice adds CORS support.

51. **No TanStack Query / Axios**, despite architecture assumption 9
    listing them as the anticipated FE libs. The task instructions for
    this slice explicitly said "keep deps minimal" — a ~40-line custom
    `useFetch` hook (`src/utils/useFetch.js`) covers every read in this
    app (loading/error/data + manual refetch + a `deps` array), and a
    plain `fetch`-based wrapper (`src/api/client.js`) covers writes and
    the 401-refresh-retry-once flow. Revisit if a future slice needs
    request deduplication/caching across components that this app
    doesn't currently need.

52. **`recharts` was added** (architecture assumption 9 names it
    explicitly) for the single equity-curve chart (design 4.13) — no
    lighter-weight alternative was considered necessary since this is
    the one chart in the whole product and recharts is a common,
    well-maintained choice with a declarative API that matches the
    design spec's line+area-fill+tooltip requirements directly.

53. **Admin per-user inspector's "Unrealized P&L (open)" stat card shows
    "Not available"** rather than a computed number. `GET
    /admin/users/{id}` (`api/app/schemas/admin.py`'s
    `UserInspectorResponse`/`AccountDetail`) does not return
    `unrealized_pnl` or per-position current/mark prices — only
    `entry_price`/`entry_date` (`PositionDetail`) — unlike `/me/account`
    and `/me/positions`, which do. Rather than fabricate a number from
    data the backend doesn't expose for this endpoint, the card is
    honest about the gap. This is a backend-response-shape limitation,
    not a frontend oversight — flagged here since design 4.8 depicts an
    "Unrealized P&L (open)" card in the admin inspector identical to the
    user dashboard's, but the two endpoints' payloads aren't actually
    symmetric.

54. **Login throttle / 401 lockout response (`"Too many failed login
    attempts..."`, also a 401 per `api/app/routers/auth.py`) is rendered
    through the same "Invalid email or password" branch** as a generic
    wrong-credential 401, rather than a distinct third error message.
    Design 4.1 mentions "an optional rate-limited/lockout notice" but
    doesn't mandate a distinct copy/state for it, and the backend itself
    returns the lockout case as a 401 with a different `detail` string —
    the frontend doesn't currently branch on `detail` text (by design,
    to avoid coupling UI logic to exact backend error strings), so this
    nuance is deferred; if a future slice wants the distinct lockout
    copy, `AuthContext.login()`'s returned `message` already carries the
    server's exact detail string and could be surfaced verbatim.

55. **CSV export (Trades Today, design 4.9) fetches through
    `src/api/client.js`'s `getText()`** (a new raw-text variant of the
    same Bearer-token + refresh-retry-once request path used by every
    other call) and triggers a download via a `Blob` + temporary `<a
    download>` click, rather than `window.open()`/a plain `<a href>`
    navigation. A direct navigation to `/admin/trades-today?format=csv`
    would not carry the in-memory `Authorization` header (only
    `client.js`'s `fetch` wrapper attaches it) and would 401. Backtest
    results' "Export CSV" button (design 4.13) was not implemented in
    this slice — the PRD/design call CSV export a non-blocking
    nice-to-have (design assumption 7); only the Trades Today export
    exists.
