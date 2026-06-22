"""Password hashing + JWT issue/verify utilities (architecture Section 6.1).

Password hashes are bcrypt via passlib (matches app/bootstrap.py's
CryptContext usage). Hashes are never logged or returned to callers.

JWTs are HS256, signed with settings.jwt_secret (PyJWT). Two kinds:
- access token: short-lived (~30 min), claims sub=user_id, role, exp.
- refresh token: longer-lived (~7 days), claims sub=user_id only (role
  is re-derived from the DB on refresh so a role change takes effect
  without waiting for the refresh token to expire).
"""

import datetime

import jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_TTL = datetime.timedelta(minutes=30)
REFRESH_TOKEN_TTL = datetime.timedelta(days=7)

JWT_ALGORITHM = "HS256"


class TokenError(Exception):
    """Raised when a JWT is missing, malformed, expired, or invalid."""


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + REFRESH_TOKEN_TTL,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict:
    """Decode + validate a JWT, raising TokenError on any problem.

    expected_type guards against an access token being replayed as a
    refresh token or vice versa.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc

    if payload.get("type") != expected_type:
        raise TokenError("Unexpected token type")

    return payload
