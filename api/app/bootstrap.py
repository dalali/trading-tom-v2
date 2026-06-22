"""Admin bootstrap seed (architecture Section 6.3, PRD Section 2.3 / FR-1).

On first backend startup, after migrations: if no role='admin' user
exists, seed exactly one from ADMIN_BOOTSTRAP_EMAIL / ADMIN_BOOTSTRAP_PASSWORD.
Idempotent (never duplicates once an admin exists). If the env vars are
absent and no admin exists, log a clear warning and skip.

Kept as a small, DB-session-agnostic function (takes a Session) so it
can be unit-tested against a sqlite in-memory DB or any SQLAlchemy
session, and called from start.sh via `python -m app.bootstrap`.
"""

import logging

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, User

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def bootstrap_admin(db: Session, email: str | None, password: str | None) -> User | None:
    """Create the first admin user if none exists yet.

    Returns the created User, or None if no admin was created (either
    because one already exists, or because env vars were missing).
    """
    existing_admin = db.execute(select(User).where(User.role == "admin")).first()
    if existing_admin is not None:
        logger.info("Admin bootstrap skipped: an admin user already exists.")
        return None

    if not email or not password:
        logger.warning(
            "ADMIN_BOOTSTRAP_EMAIL/ADMIN_BOOTSTRAP_PASSWORD not set and no "
            "admin user exists. Skipping admin bootstrap. Set these env "
            "vars and restart to create the first admin account."
        )
        return None

    admin = User(
        email=email,
        email_lower=email.lower(),
        display_name="Admin",
        password_hash=pwd_context.hash(password),
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.flush()  # populate admin.id for the Account FK below

    db.add(Account(user_id=admin.id))
    db.commit()

    logger.info("Admin bootstrap: created admin user %s", email)
    return admin
