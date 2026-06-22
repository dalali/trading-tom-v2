"""Admin bootstrap tests (architecture 6.3, PRD FR-1).

Runs against the in-memory sqlite db_session fixture (conftest.py) —
no live Postgres required.
"""

from sqlalchemy import select

from app.bootstrap import bootstrap_admin
from app.models import Account, User


def test_skips_when_env_vars_missing_and_no_admin_exists(db_session):
    result = bootstrap_admin(db_session, None, None)

    assert result is None
    assert db_session.execute(select(User)).first() is None


def test_creates_admin_when_env_vars_present_and_no_admin_exists(db_session):
    admin = bootstrap_admin(db_session, "admin@example.com", "supersecret123")

    assert admin is not None
    assert admin.role == "admin"
    assert admin.email == "admin@example.com"
    assert admin.email_lower == "admin@example.com"
    assert admin.is_active is True
    # Password must be hashed, never stored/returned in plaintext (PRD 9.1).
    assert admin.password_hash != "supersecret123"

    account = db_session.execute(select(Account).where(Account.user_id == admin.id)).scalar_one()
    assert account.cash_balance == 0


def test_idempotent_does_not_duplicate_admin_on_second_call(db_session):
    bootstrap_admin(db_session, "admin@example.com", "supersecret123")
    result = bootstrap_admin(db_session, "admin@example.com", "supersecret123")

    assert result is None
    admins = db_session.execute(select(User).where(User.role == "admin")).scalars().all()
    assert len(admins) == 1


def test_skips_seeding_again_even_with_different_env_vars_once_admin_exists(db_session):
    bootstrap_admin(db_session, "admin@example.com", "supersecret123")
    result = bootstrap_admin(db_session, "someone-else@example.com", "differentpassword")

    assert result is None
    admins = db_session.execute(select(User).where(User.role == "admin")).scalars().all()
    assert len(admins) == 1
    assert admins[0].email == "admin@example.com"
