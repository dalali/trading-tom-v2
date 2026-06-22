"""Integration tests for /auth/* (architecture 5.1) using the TestClient
+ sqlite-backed `client` fixture from conftest.py.

Each test gets a fresh throttle module state via the autouse fixture
below, since app.throttle's failure dict is module-level and would
otherwise leak lockouts across tests (and across IPs, since
TestClient's client.host is constant).
"""

import importlib

import pytest

import app.throttle as throttle_module
from app.models import Account, User
from app.security import hash_password


@pytest.fixture(autouse=True)
def _reset_throttle():
    importlib.reload(throttle_module)


def _create_user(session, email="user@example.com", password="correct-password", role="user", is_active=True):
    user = User(
        email=email,
        email_lower=email.lower(),
        display_name="Test User",
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    session.add(Account(user_id=user.id))
    session.commit()
    return user


def test_login_success_returns_token_and_sets_cookie(client, db_session_for_client):
    _create_user(db_session_for_client, email="user@example.com", password="correct-password")

    response = client.post(
        "/auth/login", json={"email": "user@example.com", "password": "correct-password"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "user"
    assert "access_token" in body and body["access_token"]
    assert "refresh_token" in response.cookies


def test_login_wrong_password_returns_generic_401(client, db_session_for_client):
    _create_user(db_session_for_client, email="user@example.com", password="correct-password")

    response = client.post(
        "/auth/login", json={"email": "user@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_unknown_email_returns_same_generic_401(client, db_session_for_client):
    response = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_inactive_user_returns_403_after_valid_credentials(client, db_session_for_client):
    _create_user(
        db_session_for_client,
        email="disabled@example.com",
        password="correct-password",
        is_active=False,
    )

    response = client.post(
        "/auth/login", json={"email": "disabled@example.com", "password": "correct-password"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Account disabled"


def test_login_throttle_locks_out_after_max_failures(client, db_session_for_client):
    _create_user(db_session_for_client, email="user@example.com", password="correct-password")

    for _ in range(throttle_module.MAX_FAILURES):
        client.post("/auth/login", json={"email": "user@example.com", "password": "wrong"})

    response = client.post(
        "/auth/login", json={"email": "user@example.com", "password": "correct-password"}
    )

    assert response.status_code == 401
    assert "Too many failed login attempts" in response.json()["detail"]


def test_refresh_returns_new_access_token(client, db_session_for_client):
    _create_user(db_session_for_client, email="user@example.com", password="correct-password")
    login_response = client.post(
        "/auth/login", json={"email": "user@example.com", "password": "correct-password"}
    )
    assert login_response.status_code == 200

    refresh_response = client.post("/auth/refresh")

    assert refresh_response.status_code == 200
    assert "access_token" in refresh_response.json()


def test_refresh_without_cookie_returns_401(client):
    response = client.post("/auth/refresh")

    assert response.status_code == 401


def test_logout_clears_cookie_and_returns_204(client, db_session_for_client):
    _create_user(db_session_for_client, email="user@example.com", password="correct-password")
    client.post("/auth/login", json={"email": "user@example.com", "password": "correct-password"})

    response = client.post("/auth/logout")

    assert response.status_code == 204
    # After logout, refresh should no longer work.
    refresh_response = client.post("/auth/refresh")
    assert refresh_response.status_code == 401


def test_me_requires_auth(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_me_returns_current_user(client, db_session_for_client):
    _create_user(db_session_for_client, email="user@example.com", password="correct-password")
    login_response = client.post(
        "/auth/login", json={"email": "user@example.com", "password": "correct-password"}
    )
    access_token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["role"] == "user"
    assert body["is_active"] is True
