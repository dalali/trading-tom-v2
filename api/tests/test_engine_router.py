"""Integration tests for /admin/engine/* (architecture 5.5) using the
TestClient + sqlite-backed `client_with_engine_runs` fixture (includes
the engine_runs table, unlike the plain `client` fixture).

No live Postgres, no real engine run / market data — trigger_manual_run
is monkeypatched where we need to simulate "a run is already in
progress" without actually running the engine.
"""

import pytest

from app.models import EngineRun, User
from app.security import hash_password


def _create_user(session, email="user@example.com", password="correct-password", role="user"):
    from app.models import Account

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
# Status
# ---------------------------------------------------------------------------


def test_status_idle_with_no_runs(client_with_engine_runs, db_session_for_client_with_engine_runs):
    headers = _admin_headers(client_with_engine_runs, db_session_for_client_with_engine_runs)

    response = client_with_engine_runs.get("/admin/engine/status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "idle"
    assert body["last_run"] is None
    assert body["next_scheduled_run"] is not None


def test_status_running_when_a_run_is_in_progress(
    client_with_engine_runs, db_session_for_client_with_engine_runs
):
    headers = _admin_headers(client_with_engine_runs, db_session_for_client_with_engine_runs)
    db_session_for_client_with_engine_runs.add(EngineRun(trigger="manual", status="running"))
    db_session_for_client_with_engine_runs.commit()

    response = client_with_engine_runs.get("/admin/engine/status", headers=headers)

    assert response.status_code == 200
    assert response.json()["state"] == "running"


# ---------------------------------------------------------------------------
# Trigger run
# ---------------------------------------------------------------------------


def test_trigger_run_returns_202_with_engine_run_id(
    client_with_engine_runs, db_session_for_client_with_engine_runs, monkeypatch
):
    headers = _admin_headers(client_with_engine_runs, db_session_for_client_with_engine_runs)

    # Avoid touching real market data / the engine runner: monkeypatch
    # trigger_manual_run at the router's import site to just create a
    # completed EngineRun row directly.
    def _fake_trigger(db, as_of_date=None):
        run = EngineRun(trigger="manual", status="complete")
        db.add(run)
        db.commit()
        return run

    monkeypatch.setattr("app.routers.engine.trigger_manual_run", _fake_trigger)

    response = client_with_engine_runs.post("/admin/engine/run", headers=headers)

    assert response.status_code == 202
    assert "engine_run_id" in response.json()


def test_trigger_run_returns_409_when_already_running(
    client_with_engine_runs, db_session_for_client_with_engine_runs, monkeypatch
):
    headers = _admin_headers(client_with_engine_runs, db_session_for_client_with_engine_runs)

    from app.scheduler import EngineRunInProgress

    def _fake_trigger(db, as_of_date=None):
        raise EngineRunInProgress("An engine run is already in progress")

    monkeypatch.setattr("app.routers.engine.trigger_manual_run", _fake_trigger)

    response = client_with_engine_runs.post("/admin/engine/run", headers=headers)

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Run history + detail
# ---------------------------------------------------------------------------


def test_list_runs_newest_first_and_paginates(
    client_with_engine_runs, db_session_for_client_with_engine_runs
):
    headers = _admin_headers(client_with_engine_runs, db_session_for_client_with_engine_runs)
    db = db_session_for_client_with_engine_runs
    for _ in range(3):
        db.add(EngineRun(trigger="scheduled", status="complete"))
    db.commit()

    response = client_with_engine_runs.get(
        "/admin/engine/runs", params={"page": 1, "page_size": 2}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3
    # newest first -> highest id first
    assert body["items"][0]["id"] > body["items"][1]["id"]


def test_get_run_detail_includes_errors(
    client_with_engine_runs, db_session_for_client_with_engine_runs
):
    headers = _admin_headers(client_with_engine_runs, db_session_for_client_with_engine_runs)
    db = db_session_for_client_with_engine_runs
    run = EngineRun(
        trigger="manual",
        status="complete",
        tickers_evaluated=5,
        signals_fired=2,
        trades_executed=1,
        users_affected=1,
        errors=[{"ticker": "AAPL", "error": "fetch failed"}],
    )
    db.add(run)
    db.commit()

    response = client_with_engine_runs.get(f"/admin/engine/runs/{run.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == [{"ticker": "AAPL", "error": "fetch failed"}]
    assert body["tickers_evaluated"] == 5


def test_get_run_detail_404_when_missing(
    client_with_engine_runs, db_session_for_client_with_engine_runs
):
    headers = _admin_headers(client_with_engine_runs, db_session_for_client_with_engine_runs)

    response = client_with_engine_runs.get("/admin/engine/runs/999999", headers=headers)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/admin/engine/status"),
        ("post", "/admin/engine/run"),
        ("get", "/admin/engine/runs"),
        ("get", "/admin/engine/runs/1"),
    ],
)
def test_non_admin_gets_403_on_engine_routes(
    client_with_engine_runs, db_session_for_client_with_engine_runs, method, path
):
    _create_user(
        db_session_for_client_with_engine_runs, email="plain@example.com", password="plain-password"
    )
    token = _login(client_with_engine_runs, "plain@example.com", "plain-password")
    headers = {"Authorization": f"Bearer {token}"}

    response = client_with_engine_runs.request(method, path, headers=headers)

    assert response.status_code == 403


def test_unauthenticated_gets_401_on_engine_routes(client_with_engine_runs):
    response = client_with_engine_runs.get("/admin/engine/status")

    assert response.status_code == 401
