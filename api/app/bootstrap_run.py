"""CLI entrypoint for admin bootstrap, invoked by start.sh:

    python -m app.bootstrap_run

Opens one real DB session, runs bootstrap_admin(), closes it. Separate
from app/bootstrap.py so the core logic stays unit-testable without a
live DB (see tests/test_bootstrap.py), while this module is the thin
"wire it to a real session and the real env vars" entrypoint.
"""

import logging

from app.bootstrap import bootstrap_admin
from app.config import settings
from app.db import SessionLocal

logging.basicConfig(level=logging.INFO)


def main() -> None:
    db = SessionLocal()
    try:
        bootstrap_admin(db, settings.admin_bootstrap_email, settings.admin_bootstrap_password)
    finally:
        db.close()


if __name__ == "__main__":
    main()
