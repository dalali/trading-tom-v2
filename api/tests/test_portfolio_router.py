"""Integration tests for /me/account, /me/positions, /me/trades, and the
admin trade-history routers (architecture 5.3/5.4) using the
TestClient + sqlite-backed `client_with_engine_runs` fixture (the admin
trades-today route joins against engine_runs).
"""

import datetime
import decimal

import pytest

from app.models import Account, EngineRun, Position, Trade, User
from app.security import hash_password


def _create_user(
    session, email="user@example.com", password="correct-password", role="user", cash="0"
):
    user = User(
        email=email,
        email_lower=email.lower(),
        display_name="Test User",
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(Account(user_id=user.id, cash_balance=decimal.Decimal(cash)))
    session.commit()
    return user


def _login(client, email, password):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(client, db_session, email, password, role="user", cash="0"):
    _create_user(db_session, email=email, password=password, role=role, cash=cash)
    token = _login(client, email, password)
    return {"Authorization": f"Bearer {token}"}


def _admin_headers(client, db_session, email="admin@example.com", password="admin-password"):
    return _headers(client, db_session, email, password, role="admin")


# ---------------------------------------------------------------------------
# /me/account
# ---------------------------------------------------------------------------


def test_my_account_zero_state_for_unfunded_user(client, db_session_for_client):
    headers = _headers(client, db_session_for_client, "zero@example.com", "password123")

    response = client.get("/me/account", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["cash_balance"] == "0.0000"
    assert body["total_value"] == "0.0000"
    assert body["unrealized_pnl"] == "0.0000"
    assert body["as_of"] is not None


def test_my_account_computes_totals_with_open_position(client, db_session_for_client):
    headers = _headers(
        client, db_session_for_client, "funded@example.com", "password123", cash="5000"
    )
    db = db_session_for_client
    user = db.query(User).filter_by(email_lower="funded@example.com").one()

    buy_trade = Trade(
        user_id=user.id,
        ticker="AAPL",
        side="BUY",
        quantity=10,
        price=decimal.Decimal("100"),
        trade_value=decimal.Decimal("1000"),
        bar_date=datetime.date(2024, 1, 2),
        signal_reason="ENTRY_TREND_MOMENTUM",
    )
    db.add(buy_trade)
    db.flush()
    db.add(
        Position(
            user_id=user.id,
            ticker="AAPL",
            quantity=10,
            entry_price=decimal.Decimal("100"),
            entry_date=datetime.date(2024, 1, 2),
            entry_trade_id=buy_trade.id,
            last_mark_price=decimal.Decimal("110"),
        )
    )
    user.account.equity_value = decimal.Decimal("1100")
    db.commit()

    response = client.get("/me/account", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["cash_balance"] == "5000.0000"
    assert body["equity_value"] == "1100.0000"
    assert body["total_value"] == "6100.0000"
    # unrealized_pnl = (110 - 100) * 10 = 100
    assert body["unrealized_pnl"] == "100.0000"


# ---------------------------------------------------------------------------
# /me/positions
# ---------------------------------------------------------------------------


def test_my_positions_computes_days_held_and_unrealized(client, db_session_for_client):
    headers = _headers(client, db_session_for_client, "pos@example.com", "password123", cash="5000")
    db = db_session_for_client
    user = db.query(User).filter_by(email_lower="pos@example.com").one()

    entry_date = datetime.date.today() - datetime.timedelta(days=4)
    buy_trade = Trade(
        user_id=user.id,
        ticker="MSFT",
        side="BUY",
        quantity=5,
        price=decimal.Decimal("200"),
        trade_value=decimal.Decimal("1000"),
        bar_date=entry_date,
        signal_reason="ENTRY_TREND_MOMENTUM",
    )
    db.add(buy_trade)
    db.flush()
    db.add(
        Position(
            user_id=user.id,
            ticker="MSFT",
            quantity=5,
            entry_price=decimal.Decimal("200"),
            entry_date=entry_date,
            entry_trade_id=buy_trade.id,
            last_mark_price=decimal.Decimal("220"),
        )
    )
    db.commit()

    response = client.get("/me/positions", headers=headers)

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    pos = items[0]
    assert pos["ticker"] == "MSFT"
    assert pos["days_held"] == 4
    assert pos["current_price"] == "220.0000"
    # (220-200)*5 = 100
    assert pos["unrealized_pnl_abs"] == "100.0000"
    assert pos["unrealized_pnl_pct"] == "10.0000"


def test_my_positions_empty_when_no_open_positions(client, db_session_for_client):
    headers = _headers(client, db_session_for_client, "nopos@example.com", "password123")

    response = client.get("/me/positions", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# /me/trades
# ---------------------------------------------------------------------------


def _add_trade(db, user_id, ticker, side, executed_at, bar_date, realized_pnl=None, **kwargs):
    trade = Trade(
        user_id=user_id,
        ticker=ticker,
        side=side,
        quantity=kwargs.get("quantity", 10),
        price=kwargs.get("price", decimal.Decimal("100")),
        trade_value=kwargs.get("trade_value", decimal.Decimal("1000")),
        executed_at=executed_at,
        bar_date=bar_date,
        signal_reason=kwargs.get("signal_reason", "ENTRY_TREND_MOMENTUM"),
        realized_pnl=realized_pnl,
        position_id=kwargs.get("position_id"),
        engine_run_id=kwargs.get("engine_run_id"),
    )
    db.add(trade)
    db.commit()
    return trade


def test_my_trades_newest_first(client, db_session_for_client):
    headers = _headers(client, db_session_for_client, "trader@example.com", "password123")
    db = db_session_for_client
    user = db.query(User).filter_by(email_lower="trader@example.com").one()

    _add_trade(
        db, user.id, "AAPL", "BUY",
        datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc), datetime.date(2024, 1, 1),
    )
    _add_trade(
        db, user.id, "MSFT", "BUY",
        datetime.datetime(2024, 1, 3, tzinfo=datetime.timezone.utc), datetime.date(2024, 1, 3),
    )

    response = client.get("/me/trades", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["ticker"] == "MSFT"
    assert body["items"][1]["ticker"] == "AAPL"


def test_my_trades_paginates(client, db_session_for_client):
    headers = _headers(client, db_session_for_client, "paginator@example.com", "password123")
    db = db_session_for_client
    user = db.query(User).filter_by(email_lower="paginator@example.com").one()

    for i in range(5):
        _add_trade(
            db, user.id, "AAPL", "BUY",
            datetime.datetime(2024, 1, i + 1, tzinfo=datetime.timezone.utc),
            datetime.date(2024, 1, i + 1),
        )

    response = client.get("/me/trades", params={"page": 1, "page_size": 2}, headers=headers)

    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5


def test_my_trades_filters_by_ticker(client, db_session_for_client):
    headers = _headers(client, db_session_for_client, "filterer@example.com", "password123")
    db = db_session_for_client
    user = db.query(User).filter_by(email_lower="filterer@example.com").one()

    _add_trade(
        db, user.id, "AAPL", "BUY",
        datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc), datetime.date(2024, 1, 1),
    )
    _add_trade(
        db, user.id, "MSFT", "BUY",
        datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc), datetime.date(2024, 1, 2),
    )

    response = client.get("/me/trades", params={"ticker": "AAPL"}, headers=headers)

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["ticker"] == "AAPL"


def test_my_trades_buy_shows_null_realized_pnl(client, db_session_for_client):
    headers = _headers(client, db_session_for_client, "buyer@example.com", "password123")
    db = db_session_for_client
    user = db.query(User).filter_by(email_lower="buyer@example.com").one()

    _add_trade(
        db, user.id, "AAPL", "BUY",
        datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc), datetime.date(2024, 1, 1),
        realized_pnl=None,
    )

    response = client.get("/me/trades", headers=headers)

    body = response.json()
    assert body["items"][0]["realized_pnl"] is None


def test_my_trades_sell_shows_realized_pnl(client, db_session_for_client):
    headers = _headers(client, db_session_for_client, "seller@example.com", "password123")
    db = db_session_for_client
    user = db.query(User).filter_by(email_lower="seller@example.com").one()

    _add_trade(
        db, user.id, "AAPL", "SELL",
        datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc), datetime.date(2024, 1, 1),
        realized_pnl=decimal.Decimal("50"),
    )

    response = client.get("/me/trades", headers=headers)

    body = response.json()
    assert body["items"][0]["realized_pnl"] == "50.0000"


# ---------------------------------------------------------------------------
# Cross-account scoping: /me/* must ignore any client-supplied user id
# ---------------------------------------------------------------------------


def test_me_trades_ignores_client_supplied_user_id(client, db_session_for_client):
    headers_a = _headers(client, db_session_for_client, "usera@example.com", "password123")
    db = db_session_for_client
    user_a = db.query(User).filter_by(email_lower="usera@example.com").one()
    user_b = _create_user(db, email="userb@example.com", password="password123")

    _add_trade(
        db, user_b.id, "TSLA", "BUY",
        datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc), datetime.date(2024, 1, 1),
    )

    # user_id is not even an accepted query param on /me/trades, but
    # assert it's silently ignored rather than somehow leaking user_b's data.
    response = client.get("/me/trades", params={"user_id": user_b.id}, headers=headers_a)

    body = response.json()
    assert body["total"] == 0


def test_me_account_ignores_client_supplied_user_id(client, db_session_for_client):
    headers_a = _headers(
        client, db_session_for_client, "usera2@example.com", "password123", cash="100"
    )
    user_b = _create_user(
        db_session_for_client, email="userb2@example.com", password="password123", cash="99999"
    )

    response = client.get("/me/account", params={"user_id": user_b.id}, headers=headers_a)

    body = response.json()
    assert body["cash_balance"] == "100.0000"


def test_me_positions_ignores_client_supplied_user_id(client, db_session_for_client):
    headers_a = _headers(client, db_session_for_client, "usera3@example.com", "password123")
    db = db_session_for_client
    user_b = _create_user(db, email="userb3@example.com", password="password123")

    buy_trade = Trade(
        user_id=user_b.id,
        ticker="GOOG",
        side="BUY",
        quantity=1,
        price=decimal.Decimal("100"),
        trade_value=decimal.Decimal("100"),
        bar_date=datetime.date(2024, 1, 1),
        signal_reason="ENTRY_TREND_MOMENTUM",
    )
    db.add(buy_trade)
    db.flush()
    db.add(
        Position(
            user_id=user_b.id,
            ticker="GOOG",
            quantity=1,
            entry_price=decimal.Decimal("100"),
            entry_date=datetime.date(2024, 1, 1),
            entry_trade_id=buy_trade.id,
        )
    )
    db.commit()

    response = client.get("/me/positions", params={"user_id": user_b.id}, headers=headers_a)

    assert response.json() == []


# ---------------------------------------------------------------------------
# /admin/users/{id}/trades
# ---------------------------------------------------------------------------


def test_admin_user_trades_works_for_admin(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    db = db_session_for_client
    target = _create_user(db, email="target@example.com", password="password123")
    _add_trade(
        db, target.id, "AAPL", "BUY",
        datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc), datetime.date(2024, 1, 1),
    )

    response = client.get(f"/admin/users/{target.id}/trades", headers=headers)

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_admin_user_trades_403_for_non_admin(client, db_session_for_client):
    headers = _headers(client, db_session_for_client, "plain2@example.com", "password123")
    db = db_session_for_client
    target = _create_user(db, email="target2@example.com", password="password123")

    response = client.get(f"/admin/users/{target.id}/trades", headers=headers)

    assert response.status_code == 403


def test_admin_user_trades_404_for_missing_user(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)

    response = client.get("/admin/users/999999/trades", headers=headers)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /admin/trades-today
# ---------------------------------------------------------------------------


def test_admin_trades_today_returns_feed_and_summary(
    client_with_engine_runs, db_session_for_client_with_engine_runs
):
    headers = _admin_headers(client_with_engine_runs, db_session_for_client_with_engine_runs)
    db = db_session_for_client_with_engine_runs
    target = _create_user(db, email="today@example.com", password="password123")

    run = EngineRun(
        trigger="scheduled",
        status="complete",
        tickers_evaluated=10,
        signals_fired=3,
        trades_executed=1,
        users_affected=1,
        errors=[],
    )
    db.add(run)
    db.commit()

    _add_trade(
        db, target.id, "AAPL", "BUY",
        datetime.datetime.now(datetime.timezone.utc), datetime.date.today(),
        engine_run_id=run.id,
    )

    response = client_with_engine_runs.get("/admin/trades-today", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["trades"] == 1
    assert body["summary"]["users_evaluated"] == 1
    assert len(body["items"]) == 1


def test_admin_trades_today_csv_format(
    client_with_engine_runs, db_session_for_client_with_engine_runs
):
    headers = _admin_headers(client_with_engine_runs, db_session_for_client_with_engine_runs)
    db = db_session_for_client_with_engine_runs
    target = _create_user(db, email="csvuser@example.com", password="password123")

    run = EngineRun(trigger="scheduled", status="complete")
    db.add(run)
    db.commit()

    _add_trade(
        db, target.id, "AAPL", "BUY",
        datetime.datetime.now(datetime.timezone.utc), datetime.date.today(),
        engine_run_id=run.id,
    )

    response = client_with_engine_runs.get(
        "/admin/trades-today", params={"format": "csv"}, headers=headers
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "AAPL" in response.text


def test_admin_trades_today_403_for_non_admin(
    client_with_engine_runs, db_session_for_client_with_engine_runs
):
    headers = _headers(
        client_with_engine_runs, db_session_for_client_with_engine_runs,
        "plain3@example.com", "password123",
    )

    response = client_with_engine_runs.get("/admin/trades-today", headers=headers)

    assert response.status_code == 403
