"""require_auth / require_admin dependency tests (architecture 6.2).

Exercised directly (not through the test HTTP client) since they are
plain callables that take a credentials object + db session.
"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.deps import require_admin, require_auth
from app.models import Account, User
from app.security import create_access_token


def _make_user(db_session, role="user", is_active=True, email="u@example.com"):
    user = User(
        email=email,
        email_lower=email.lower(),
        display_name="Test User",
        password_hash="irrelevant-hash",
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(Account(user_id=user.id))
    db_session.commit()
    return user


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_require_auth_returns_user_for_valid_token(db_session):
    user = _make_user(db_session)
    token = create_access_token(user.id, user.role)

    result = require_auth(credentials=_bearer(token), db=db_session)

    assert result.id == user.id


def test_require_auth_rejects_missing_credentials(db_session):
    with pytest.raises(HTTPException) as exc_info:
        require_auth(credentials=None, db=db_session)

    assert exc_info.value.status_code == 401


def test_require_auth_rejects_expired_token(db_session, monkeypatch):
    import datetime

    import jwt as pyjwt

    from app.config import settings

    user = _make_user(db_session)
    now = datetime.datetime.now(datetime.timezone.utc)
    expired_token = pyjwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "type": "access",
            "iat": now - datetime.timedelta(minutes=60),
            "exp": now - datetime.timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc_info:
        require_auth(credentials=_bearer(expired_token), db=db_session)

    assert exc_info.value.status_code == 401


def test_require_auth_rejects_inactive_user(db_session):
    user = _make_user(db_session, is_active=False)
    token = create_access_token(user.id, user.role)

    with pytest.raises(HTTPException) as exc_info:
        require_auth(credentials=_bearer(token), db=db_session)

    assert exc_info.value.status_code == 401


def test_require_admin_allows_admin(db_session):
    user = _make_user(db_session, role="admin")

    result = require_admin(user=user)

    assert result.id == user.id


def test_require_admin_rejects_non_admin(db_session):
    user = _make_user(db_session, role="user")

    with pytest.raises(HTTPException) as exc_info:
        require_admin(user=user)

    assert exc_info.value.status_code == 403
