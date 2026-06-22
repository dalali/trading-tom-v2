"""FastAPI dependencies: DB session, current-user auth, role guards.

Per architecture Section 6.2:
- require_auth decodes/validates the access token, rejects expired
  tokens and inactive users, and injects the current user.
- require_admin builds on require_auth and additionally asserts
  role == 'admin'.

These are imported by every future protected router (this slice's
/auth/me, and later /admin/* and /me/* routes).
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import TokenError, decode_token

bearer_scheme = HTTPBearer(auto_error=False)

# Re-exported so routers can `from app.deps import get_db` alongside the
# auth dependencies below, without also importing from app.db directly.
__all__ = ["get_db", "require_auth", "require_admin"]


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode the Bearer access token and return the current active user.

    401 if the header is missing, the token is malformed/expired, or
    the referenced user no longer exists. 401 (not 403) for inactive
    users too — architecture 6.2 says require_auth rejects inactive
    users; the inactive-vs-bad-credentials distinction at 403 is only
    surfaced at /auth/login (architecture 5.1/9.1), not on every
    subsequent authenticated request.
    """
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return user


def require_admin(user: User = Depends(require_auth)) -> User:
    """Additionally assert role == 'admin', else 403 (architecture 6.2, FR-12 AC1)."""
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user
