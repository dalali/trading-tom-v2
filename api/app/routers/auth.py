"""Auth router (architecture Section 5.1 / 6).

POST /auth/login   - verify credentials, issue access token, set
                      refresh_token HttpOnly cookie.
POST /auth/refresh  - read refresh cookie, issue a new access token.
POST /auth/logout   - clear the refresh cookie.
GET  /auth/me       - return the current authenticated user.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, require_auth
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, RefreshResponse
from app.security import (
    REFRESH_TOKEN_TTL,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.throttle import check_locked, record_failure, record_success

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"

# Assumption: "Secure off for local" (task spec) — this is a local-only
# MVP deployment over HTTP (architecture 9.2 "No HTTPS locally"), so the
# refresh cookie is not marked Secure. Revisit before any non-local
# deployment, per architecture 6.1 "Secure-in-prod".
_REFRESH_COOKIE_KWARGS = {
    "httponly": True,
    "samesite": "lax",
    "secure": False,
    "path": "/",
}


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        **_REFRESH_COOKIE_KWARGS,
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    email_key = body.email.lower()

    if check_locked(client_ip, email_key):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Too many failed login attempts. Try again later.",
        )

    user = db.execute(select(User).where(User.email_lower == email_key)).scalar_one_or_none()

    # Generic failure for unknown email or wrong password — do not reveal
    # whether the email exists (architecture 9.1 / FR-8 AC2).
    if user is None or not verify_password(body.password, user.password_hash):
        record_failure(client_ip, email_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    # Credentials are valid at this point. Only now is is_active checked,
    # so a disabled account gets a distinct message (architecture 9.1 /
    # FR-8 AC3) rather than leaking that distinction to a wrong password.
    if not user.is_active:
        record_failure(client_ip, email_key)
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account disabled")

    record_success(client_ip, email_key)

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)

    return LoginResponse(access_token=access_token, role=user.role, user_id=user.id)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(request: Request, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    # Role is re-derived from the DB (not trusted from the refresh token)
    # so a role change takes effect on the next refresh, not just on
    # next full login.
    access_token = create_access_token(user.id, user.role)
    return RefreshResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    # Must mutate the injected `response` (which FastAPI actually sends)
    # rather than return a new Response object, or the Set-Cookie header
    # added by delete_cookie is discarded.
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(require_auth)):
    return MeResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )
