"""Integration tests for /admin/users* (architecture 5.2) using the
TestClient + sqlite-backed `client` fixture from conftest.py.

No live Postgres — same pattern as test_auth_router.py.
"""

import decimal

import pytest

from app.models import Account, FundTransaction, User
from app.security import hash_password


def _create_user(
    session, email="user@example.com", password="correct-password", role="user", is_active=True
):
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


def _login(client, email, password):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _admin_headers(client, db_session, email="admin@example.com", password="admin-password"):
    _create_user(db_session, email=email, password=password, role="admin")
    token = _login(client, email, password)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Create user
# ---------------------------------------------------------------------------


def test_create_user_success_returns_201(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)

    response = client.post(
        "/admin/users",
        json={
            "email": "new@example.com",
            "display_name": "New User",
            "password": "valid-password",
            "role": "user",
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "user"
    assert body["is_active"] is True

    # 1:1 account created with cash_balance = 0 (PRD 3.1).
    created = db_session_for_client.query(User).filter_by(email_lower="new@example.com").one()
    assert created.account is not None
    assert created.account.cash_balance == decimal.Decimal("0")


def test_create_user_duplicate_email_returns_409(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    _create_user(db_session_for_client, email="dup@example.com")

    response = client.post(
        "/admin/users",
        json={
            "email": "DUP@example.com",  # case-insensitive duplicate
            "display_name": "Dup User",
            "password": "valid-password",
            "role": "user",
        },
        headers=headers,
    )

    assert response.status_code == 409


def test_create_user_weak_password_returns_400(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)

    response = client.post(
        "/admin/users",
        json={
            "email": "weak@example.com",
            "display_name": "Weak Pw",
            "password": "short",
            "role": "user",
        },
        headers=headers,
    )

    assert response.status_code == 400


def test_create_user_bad_email_returns_400(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)

    response = client.post(
        "/admin/users",
        json={
            "email": "not-an-email",
            "display_name": "Bad Email",
            "password": "valid-password",
            "role": "user",
        },
        headers=headers,
    )

    assert response.status_code == 400


def test_create_user_invalid_role_returns_400(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)

    response = client.post(
        "/admin/users",
        json={
            "email": "weird-role@example.com",
            "display_name": "Weird Role",
            "password": "valid-password",
            "role": "superadmin",
        },
        headers=headers,
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# RBAC: non-admin hitting any /admin route
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path_suffix",
    [
        ("get", ""),
        ("post", ""),
        ("get", "/1"),
        ("delete", "/1"),
        ("post", "/1/fund"),
    ],
)
def test_non_admin_gets_403_on_admin_routes(client, db_session_for_client, method, path_suffix):
    _create_user(db_session_for_client, email="plain@example.com", password="plain-password")
    token = _login(client, "plain@example.com", "plain-password")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.request(method, f"/admin/users{path_suffix}", headers=headers, json={})

    assert response.status_code == 403


def test_unauthenticated_gets_401_on_admin_routes(client):
    response = client.get("/admin/users")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Fund
# ---------------------------------------------------------------------------


def test_fund_positive_amount_updates_balance_and_ledger(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    target = _create_user(db_session_for_client, email="target@example.com")

    response = client.post(
        f"/admin/users/{target.id}/fund", json={"amount": "1000.50"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["new_balance"] == "1000.5000"

    db_session_for_client.refresh(target.account)
    assert target.account.cash_balance == decimal.Decimal("1000.50")

    ledger_rows = (
        db_session_for_client.query(FundTransaction).filter_by(user_id=target.id).all()
    )
    assert len(ledger_rows) == 1
    assert ledger_rows[0].amount == decimal.Decimal("1000.50")
    assert ledger_rows[0].resulting_balance == decimal.Decimal("1000.50")


def test_fund_accumulates_across_multiple_calls(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    target = _create_user(db_session_for_client, email="target2@example.com")

    client.post(f"/admin/users/{target.id}/fund", json={"amount": "100"}, headers=headers)
    response = client.post(
        f"/admin/users/{target.id}/fund", json={"amount": "50"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["new_balance"] == "150.0000"


def test_fund_zero_or_negative_returns_400(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    target = _create_user(db_session_for_client, email="target3@example.com")

    zero_response = client.post(
        f"/admin/users/{target.id}/fund", json={"amount": "0"}, headers=headers
    )
    negative_response = client.post(
        f"/admin/users/{target.id}/fund", json={"amount": "-10"}, headers=headers
    )

    assert zero_response.status_code == 400
    assert negative_response.status_code == 400


def test_fund_unknown_user_returns_404(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)

    response = client.post(
        "/admin/users/999999/fund", json={"amount": "100"}, headers=headers
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Soft delete / last-admin guard
# ---------------------------------------------------------------------------


def test_deactivate_user_sets_is_active_false(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    target = _create_user(db_session_for_client, email="todeactivate@example.com")

    response = client.delete(f"/admin/users/{target.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["is_active"] is False

    db_session_for_client.refresh(target)
    assert target.is_active is False


def test_deactivate_last_active_admin_returns_409(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client, email="onlyadmin@example.com")
    only_admin = (
        db_session_for_client.query(User).filter_by(email_lower="onlyadmin@example.com").one()
    )

    response = client.delete(f"/admin/users/{only_admin.id}", headers=headers)

    assert response.status_code == 409


def test_deactivate_one_of_two_admins_succeeds(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client, email="admin1@example.com")
    second_admin = _create_user(
        db_session_for_client, email="admin2@example.com", password="pw12345678", role="admin"
    )

    response = client.delete(f"/admin/users/{second_admin.id}", headers=headers)

    assert response.status_code == 200


def test_deactivate_unknown_user_returns_404(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)

    response = client.delete("/admin/users/999999", headers=headers)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Inspector
# ---------------------------------------------------------------------------


def test_inspector_returns_deactivated_user(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    target = _create_user(
        db_session_for_client, email="deactivated@example.com", is_active=False
    )

    response = client.get(f"/admin/users/{target.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["is_active"] is False
    assert body["positions"] == []


def test_inspector_unknown_user_returns_404(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)

    response = client.get("/admin/users/999999", headers=headers)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# List: filters, search, pagination
# ---------------------------------------------------------------------------


def test_list_users_filters_by_status(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    _create_user(db_session_for_client, email="active1@example.com")
    _create_user(db_session_for_client, email="inactive1@example.com", is_active=False)

    active_response = client.get("/admin/users", params={"status": "active"}, headers=headers)
    deactivated_response = client.get(
        "/admin/users", params={"status": "deactivated"}, headers=headers
    )

    active_emails = {item["email"] for item in active_response.json()["items"]}
    deactivated_emails = {item["email"] for item in deactivated_response.json()["items"]}

    assert "active1@example.com" in active_emails
    assert "inactive1@example.com" not in active_emails
    assert "inactive1@example.com" in deactivated_emails
    assert "active1@example.com" not in deactivated_emails


def test_list_users_filters_by_query(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    _create_user(db_session_for_client, email="findme@example.com")
    _create_user(db_session_for_client, email="other@example.com")

    response = client.get("/admin/users", params={"q": "findme"}, headers=headers)

    emails = {item["email"] for item in response.json()["items"]}
    assert "findme@example.com" in emails
    assert "other@example.com" not in emails


def test_list_users_paginates(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    for i in range(5):
        _create_user(db_session_for_client, email=f"user{i}@example.com")

    response = client.get(
        "/admin/users", params={"page": 1, "page_size": 2}, headers=headers
    )

    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] >= 6  # 5 created + 1 admin from _admin_headers


def test_list_users_includes_total_value(client, db_session_for_client):
    headers = _admin_headers(client, db_session_for_client)
    target = _create_user(db_session_for_client, email="funded@example.com")
    client.post(f"/admin/users/{target.id}/fund", json={"amount": "500"}, headers=headers)

    response = client.get("/admin/users", params={"q": "funded"}, headers=headers)

    item = response.json()["items"][0]
    assert item["total_value"] == "500.0000"
