"""Password hashing + JWT utility tests (architecture 6.1)."""

import datetime

import jwt
import pytest

from app.config import settings
from app.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_password_round_trip():
    hashed = hash_password("supersecret123")

    assert hashed != "supersecret123"
    assert verify_password("supersecret123", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("supersecret123")

    assert verify_password("wrong-password", hashed) is False


def test_access_token_issue_and_decode_round_trip():
    token = create_access_token(user_id=42, role="admin")

    payload = decode_token(token, expected_type="access")

    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_refresh_token_issue_and_decode_round_trip():
    token = create_refresh_token(user_id=7)

    payload = decode_token(token, expected_type="refresh")

    assert payload["sub"] == "7"
    assert payload["type"] == "refresh"


def test_decode_token_rejects_expired_token():
    now = datetime.datetime.now(datetime.timezone.utc)
    expired_payload = {
        "sub": "1",
        "role": "user",
        "type": "access",
        "iat": now - datetime.timedelta(minutes=60),
        "exp": now - datetime.timedelta(minutes=30),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm="HS256")

    with pytest.raises(TokenError):
        decode_token(expired_token, expected_type="access")


def test_decode_token_rejects_wrong_token_type():
    refresh_token = create_refresh_token(user_id=1)

    with pytest.raises(TokenError):
        decode_token(refresh_token, expected_type="access")


def test_decode_token_rejects_malformed_token():
    with pytest.raises(TokenError):
        decode_token("not-a-real-token", expected_type="access")


def test_decode_token_rejects_wrong_signature():
    token = jwt.encode(
        {"sub": "1", "type": "access", "exp": datetime.datetime.now(datetime.timezone.utc)
         + datetime.timedelta(minutes=30)},
        "a-different-secret",
        algorithm="HS256",
    )

    with pytest.raises(TokenError):
        decode_token(token, expected_type="access")
