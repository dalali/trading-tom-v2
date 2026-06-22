"""Tests for the backtest feature (architecture 4.6, 5.6, 5.7; PRD
Section 6): the service layer in app/engine/backtest.py and the
/admin/backtests* + /admin/market-data/range router.

No live Postgres, no real network call — market data is pre-seeded into
market_data_cache (sqlite-backed), same approach as
tests/test_engine_runner.py. Covers: queue->running->complete happy
path, isolation from live trades/positions/accounts, validation errors
(end<=start), and admin-only access.
"""

import datetime
import decimal

import pytest
import sqlalchemy as sa

from app import strategy_config
from app.engine.backtest import (
    BacktestValidationError,
    execute_backtest,
    get_market_data_range,
    run_backtest,
    validate_date_range,
)
from app.models import Account, BacktestRun, BacktestTrade, MarketDataCache, Position, Trade, User
from app.security import hash_password

START = datetime.date(2024, 1, 1)
END = datetime.date(2024, 6, 3)


def _trending_up_closes():
    """Same engineered pattern as tests/test_engine_runner.py's
    _trending_up_closes: a gentle uptrend with a pullback then a pop on
    the final bar, so all three entry conditions hold simultaneously on
    the last bar (deterministic ENTRY_TREND_MOMENTUM signal).
    """
    closes = [100.0 + i * 0.2 for i in range(55)]
    for _ in range(4):
        closes.append(closes[-1] - 1.0)
    closes.append(closes[-1] + 5)
    return closes


def _seed_cache(db, ticker, closes, start_date):
    d = start_date
    for c in closes:
        db.add(
            MarketDataCache(
                ticker=ticker,
                bar_date=d,
                open=decimal.Decimal(str(c)),
                high=decimal.Decimal(str(c)),
                low=decimal.Decimal(str(c)),
                close=decimal.Decimal(str(c)),
                volume=1_000_000,
                provider="fake",
            )
        )
        d += datetime.timedelta(days=1)
    db.commit()


def _create_user(session, email="admin@example.com", password="admin-password", role="admin"):
    user = User(
        email=email,
        email_lower=email.lower(),
        display_name="Test Admin",
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(Account(user_id=user.id))
    session.commit()
    return user


def _login(client, email, password):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _admin_headers(client, db_session, email="admin@example.com", password="admin-password"):
    _create_user(db_session, email=email, password=password, role="admin")
    token = _login(client, email, password)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Service layer: run_backtest()
# ---------------------------------------------------------------------------


def test_run_backtest_enters_position_on_signal_and_builds_equity_curve(db_session_with_backtest_runs):
    db = db_session_with_backtest_runs
    ticker = strategy_config.UNIVERSE[0]
    closes = _trending_up_closes()
    start_date = END - datetime.timedelta(days=len(closes) - 1)
    _seed_cache(db, ticker, closes, start_date)

    run = BacktestRun(
        created_by=1,
        start_date=start_date,
        end_date=END,
        tickers=[ticker],
        starting_capital=decimal.Decimal("100000"),
        status="running",
    )
    db.add(run)
    db.commit()

    summary = run_backtest(
        db,
        run.id,
        start_date,
        END,
        [ticker],
        decimal.Decimal("100000"),
    )

    trades = db.execute(
        sa.select(BacktestTrade).where(BacktestTrade.backtest_run_id == run.id)
    ).scalars().all()

    assert summary["total_trades"] == 1
    assert len(trades) == 1
    assert trades[0].side == "BUY"
    assert trades[0].signal_reason == "ENTRY_TREND_MOMENTUM"
    assert len(summary["equity_curve"]) > 0
    # Equity curve's last point reflects cash + mark-to-market position.
    last_point = summary["equity_curve"][-1]
    assert decimal.Decimal(last_point["total_value"]) > 0


def test_run_backtest_writes_only_backtest_tables_never_live_tables(db_session_with_backtest_runs):
    """Isolation is a hard requirement (architecture 3.2/9.1 assumption
    14): a backtest must never create rows in trades/positions/accounts.
    """
    db = db_session_with_backtest_runs
    user = _create_user(db, email="liveuser@example.com")
    live_account = db.execute(sa.select(Account).where(Account.user_id == user.id)).scalar_one()
    live_cash_before = live_account.cash_balance

    ticker = strategy_config.UNIVERSE[0]
    closes = _trending_up_closes()
    start_date = END - datetime.timedelta(days=len(closes) - 1)
    _seed_cache(db, ticker, closes, start_date)

    run = BacktestRun(
        created_by=user.id,
        start_date=start_date,
        end_date=END,
        tickers=[ticker],
        starting_capital=decimal.Decimal("100000"),
        status="running",
    )
    db.add(run)
    db.commit()

    run_backtest(db, run.id, start_date, END, [ticker], decimal.Decimal("100000"))

    db.refresh(live_account)
    live_trades = db.execute(sa.select(Trade)).scalars().all()
    live_positions = db.execute(sa.select(Position)).scalars().all()

    assert live_trades == []
    assert live_positions == []
    assert live_account.cash_balance == live_cash_before

    backtest_trades = db.execute(
        sa.select(BacktestTrade).where(BacktestTrade.backtest_run_id == run.id)
    ).scalars().all()
    assert len(backtest_trades) == 1


def test_run_backtest_computes_win_rate_from_profitable_round_trip(db_session_with_backtest_runs):
    """A full BUY then a profit-target SELL should produce one closed,
    winning round-trip and a 100% win rate (PRD 6.4).
    """
    db = db_session_with_backtest_runs
    ticker = strategy_config.UNIVERSE[0]
    closes = _trending_up_closes()
    # Profit-target exit (+8%): push the price up sharply after the entry
    # bar so check_exit's PROFIT_TARGET_PCT condition fires on day 2.
    entry_close = closes[-1]
    closes.append(entry_close * 1.15)
    start_date = END - datetime.timedelta(days=len(closes) - 1)
    _seed_cache(db, ticker, closes, start_date)

    run = BacktestRun(
        created_by=1,
        start_date=start_date,
        end_date=END,
        tickers=[ticker],
        starting_capital=decimal.Decimal("100000"),
        status="running",
    )
    db.add(run)
    db.commit()

    summary = run_backtest(db, run.id, start_date, END, [ticker], decimal.Decimal("100000"))

    trades = db.execute(
        sa.select(BacktestTrade)
        .where(BacktestTrade.backtest_run_id == run.id)
        .order_by(BacktestTrade.bar_date)
    ).scalars().all()

    assert [t.side for t in trades] == ["BUY", "SELL"]
    assert trades[1].signal_reason == "EXIT_PROFIT_TARGET"
    assert trades[1].realized_pnl > 0
    assert summary["win_rate"] == decimal.Decimal("100")
    assert summary["avg_holding_days"] is not None


# ---------------------------------------------------------------------------
# Service layer: execute_backtest() lifecycle
# ---------------------------------------------------------------------------


def test_execute_backtest_transitions_queued_to_complete(db_session_with_backtest_runs):
    db = db_session_with_backtest_runs
    ticker = strategy_config.UNIVERSE[0]
    closes = _trending_up_closes()
    start_date = END - datetime.timedelta(days=len(closes) - 1)
    _seed_cache(db, ticker, closes, start_date)

    run = BacktestRun(
        created_by=1,
        start_date=start_date,
        end_date=END,
        tickers=[ticker],
        starting_capital=decimal.Decimal("100000"),
        status="queued",
    )
    db.add(run)
    db.commit()

    execute_backtest(run.id, start_date, END, [ticker], decimal.Decimal("100000"), db=db)

    db.refresh(run)
    assert run.status == "complete"
    assert run.finished_at is not None
    assert run.total_trades == 1
    assert run.equity_curve is not None
    assert len(run.equity_curve) > 0


def test_execute_backtest_marks_failed_on_unexpected_error(db_session_with_backtest_runs, monkeypatch):
    db = db_session_with_backtest_runs
    run = BacktestRun(
        created_by=1,
        start_date=START,
        end_date=END,
        tickers=["AAPL"],
        starting_capital=decimal.Decimal("100000"),
        status="queued",
    )
    db.add(run)
    db.commit()

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr("app.engine.backtest.run_backtest", _boom)

    execute_backtest(run.id, START, END, ["AAPL"], decimal.Decimal("100000"), db=db)

    db.refresh(run)
    assert run.status == "failed"
    assert run.finished_at is not None


# ---------------------------------------------------------------------------
# Service layer: validate_date_range() / get_market_data_range()
# ---------------------------------------------------------------------------


def test_validate_date_range_rejects_end_before_start(db_session_with_backtest_runs):
    with pytest.raises(BacktestValidationError):
        validate_date_range(db_session_with_backtest_runs, END, START, ["AAPL"])


def test_validate_date_range_rejects_end_equal_start(db_session_with_backtest_runs):
    with pytest.raises(BacktestValidationError):
        validate_date_range(db_session_with_backtest_runs, START, START, ["AAPL"])


def test_validate_date_range_rejects_outside_provider_range(db_session_with_backtest_runs):
    db = db_session_with_backtest_runs
    _seed_cache(db, "AAPL", [100.0] * 5, datetime.date(2024, 1, 1))

    with pytest.raises(BacktestValidationError):
        validate_date_range(
            db,
            datetime.date(2030, 1, 1),
            datetime.date(2030, 2, 1),
            ["AAPL"],
        )


def test_validate_date_range_allows_overlapping_range(db_session_with_backtest_runs):
    db = db_session_with_backtest_runs
    _seed_cache(db, "AAPL", [100.0] * 5, datetime.date(2024, 1, 1))

    # Should not raise: requested range overlaps cached data.
    validate_date_range(db, datetime.date(2024, 1, 1), datetime.date(2024, 1, 10), ["AAPL"])


def test_get_market_data_range_empty_cache_returns_none(db_session_with_backtest_runs):
    earliest, latest = get_market_data_range(db_session_with_backtest_runs, ["AAPL"])
    assert earliest is None
    assert latest is None


def test_get_market_data_range_returns_min_max(db_session_with_backtest_runs):
    db = db_session_with_backtest_runs
    _seed_cache(db, "AAPL", [100.0] * 10, datetime.date(2024, 1, 1))

    earliest, latest = get_market_data_range(db, ["AAPL"])

    assert earliest == datetime.date(2024, 1, 1)
    assert latest == datetime.date(2024, 1, 10)


# ---------------------------------------------------------------------------
# HTTP: POST /admin/backtests
# ---------------------------------------------------------------------------


def test_create_backtest_returns_202_and_queues_run(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs, monkeypatch
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)

    # Avoid touching BackgroundTasks/real execution at the HTTP layer:
    # monkeypatch execute_backtest at the router's import site.
    calls = []
    monkeypatch.setattr(
        "app.routers.backtest.execute_backtest",
        lambda *args, **kwargs: calls.append(args),
    )

    response = client_with_backtest_runs.post(
        "/admin/backtests",
        json={"start_date": "2024-01-01", "end_date": "2024-02-01", "tickers": ["AAPL"]},
        headers=headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert "backtest_run_id" in body

    run = db_session_for_client_with_backtest_runs.get(BacktestRun, body["backtest_run_id"])
    assert run is not None
    assert run.status == "queued"
    assert run.tickers == ["AAPL"]


def test_create_backtest_defaults_tickers_to_full_universe(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs, monkeypatch
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)
    monkeypatch.setattr("app.routers.backtest.execute_backtest", lambda *a, **k: None)

    response = client_with_backtest_runs.post(
        "/admin/backtests",
        json={"start_date": "2024-01-01", "end_date": "2024-02-01"},
        headers=headers,
    )

    assert response.status_code == 202
    run = db_session_for_client_with_backtest_runs.get(
        BacktestRun, response.json()["backtest_run_id"]
    )
    assert run.tickers == strategy_config.UNIVERSE


def test_create_backtest_rejects_end_before_start(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs, monkeypatch
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)
    monkeypatch.setattr("app.routers.backtest.execute_backtest", lambda *a, **k: None)

    response = client_with_backtest_runs.post(
        "/admin/backtests",
        json={"start_date": "2024-02-01", "end_date": "2024-01-01", "tickers": ["AAPL"]},
        headers=headers,
    )

    assert response.status_code == 400


def test_create_backtest_rejects_zero_starting_capital(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs, monkeypatch
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)
    monkeypatch.setattr("app.routers.backtest.execute_backtest", lambda *a, **k: None)

    response = client_with_backtest_runs.post(
        "/admin/backtests",
        json={
            "start_date": "2024-01-01",
            "end_date": "2024-02-01",
            "tickers": ["AAPL"],
            "starting_capital": "0",
        },
        headers=headers,
    )

    assert response.status_code == 400


def test_create_backtest_rejects_out_of_provider_range(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs, monkeypatch
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)
    monkeypatch.setattr("app.routers.backtest.execute_backtest", lambda *a, **k: None)
    _seed_cache(
        db_session_for_client_with_backtest_runs, "AAPL", [100.0] * 5, datetime.date(2024, 1, 1)
    )

    response = client_with_backtest_runs.post(
        "/admin/backtests",
        json={"start_date": "2030-01-01", "end_date": "2030-02-01", "tickers": ["AAPL"]},
        headers=headers,
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# HTTP: GET /admin/backtests, /admin/backtests/{id}
# ---------------------------------------------------------------------------


def test_list_backtests_newest_first_and_paginates(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)
    db = db_session_for_client_with_backtest_runs
    for _ in range(3):
        db.add(
            BacktestRun(
                created_by=1,
                start_date=START,
                end_date=END,
                tickers=["AAPL"],
                starting_capital=decimal.Decimal("100000"),
                status="complete",
            )
        )
    db.commit()

    response = client_with_backtest_runs.get(
        "/admin/backtests", params={"page": 1, "page_size": 2}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3
    assert body["items"][0]["id"] > body["items"][1]["id"]


def test_get_backtest_detail_includes_equity_curve_and_trades(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)
    db = db_session_for_client_with_backtest_runs
    run = BacktestRun(
        created_by=1,
        start_date=START,
        end_date=END,
        tickers=["AAPL"],
        starting_capital=decimal.Decimal("100000"),
        status="complete",
        total_return_pct=decimal.Decimal("5.0"),
        total_return_abs=decimal.Decimal("5000"),
        win_rate=decimal.Decimal("100"),
        total_trades=2,
        max_drawdown_pct=decimal.Decimal("1.0"),
        max_drawdown_abs=decimal.Decimal("1000"),
        avg_holding_days=decimal.Decimal("5"),
        equity_curve=[{"date": "2024-01-01", "total_value": "100000"}],
    )
    db.add(run)
    db.flush()
    db.add(
        BacktestTrade(
            backtest_run_id=run.id,
            ticker="AAPL",
            side="BUY",
            quantity=10,
            price=decimal.Decimal("100"),
            trade_value=decimal.Decimal("1000"),
            bar_date=START,
            signal_reason="ENTRY_TREND_MOMENTUM",
            realized_pnl=None,
        )
    )
    db.commit()

    response = client_with_backtest_runs.get(f"/admin/backtests/{run.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["total_trades"] == 2
    assert len(body["equity_curve"]) == 1
    assert len(body["backtest_trades"]) == 1
    assert body["backtest_trades"][0]["side"] == "BUY"


def test_get_backtest_404_when_missing(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)

    response = client_with_backtest_runs.get("/admin/backtests/999999", headers=headers)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# HTTP: GET /admin/market-data/range
# ---------------------------------------------------------------------------


def test_market_data_range_empty_cache(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)

    response = client_with_backtest_runs.get("/admin/market-data/range", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"earliest": None, "latest": None}


def test_market_data_range_returns_cached_bounds(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)
    _seed_cache(
        db_session_for_client_with_backtest_runs, "AAPL", [100.0] * 10, datetime.date(2024, 1, 1)
    )

    response = client_with_backtest_runs.get("/admin/market-data/range", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["earliest"] == "2024-01-01"
    assert body["latest"] == "2024-01-10"


# ---------------------------------------------------------------------------
# HTTP: GET /admin/market-data/universe
# ---------------------------------------------------------------------------


def test_market_data_universe_returns_configured_tickers(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs
):
    headers = _admin_headers(client_with_backtest_runs, db_session_for_client_with_backtest_runs)

    response = client_with_backtest_runs.get("/admin/market-data/universe", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0
    assert all(isinstance(ticker, str) for ticker in body)
    assert body == strategy_config.UNIVERSE


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/admin/backtests"),
        ("get", "/admin/backtests"),
        ("get", "/admin/backtests/1"),
        ("get", "/admin/market-data/range"),
        ("get", "/admin/market-data/universe"),
    ],
)
def test_non_admin_gets_403_on_backtest_routes(
    client_with_backtest_runs, db_session_for_client_with_backtest_runs, method, path
):
    user = User(
        email="plain@example.com",
        email_lower="plain@example.com",
        display_name="Plain",
        password_hash=hash_password("plain-password"),
        role="user",
        is_active=True,
    )
    db_session_for_client_with_backtest_runs.add(user)
    db_session_for_client_with_backtest_runs.flush()
    db_session_for_client_with_backtest_runs.add(Account(user_id=user.id))
    db_session_for_client_with_backtest_runs.commit()

    token = _login(client_with_backtest_runs, "plain@example.com", "plain-password")
    headers = {"Authorization": f"Bearer {token}"}

    if method == "post":
        response = client_with_backtest_runs.post(
            path,
            json={"start_date": "2024-01-01", "end_date": "2024-02-01", "tickers": ["AAPL"]},
            headers=headers,
        )
    else:
        response = client_with_backtest_runs.request(method, path, headers=headers)

    assert response.status_code == 403


def test_unauthenticated_gets_401_on_backtest_routes(client_with_backtest_runs):
    response = client_with_backtest_runs.get("/admin/backtests")

    assert response.status_code == 401
