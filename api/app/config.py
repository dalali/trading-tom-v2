"""App-level settings, loaded from environment (.env via docker-compose env_file).

Per architecture Section 8.1: required keys are DATABASE_URL, JWT_SECRET,
ADMIN_BOOTSTRAP_EMAIL, ADMIN_BOOTSTRAP_PASSWORD. MARKET_DATA_API_KEY is
optional (only consumed by the Alpha Vantage fallback adapter, not built
in this slice).

Assumption: ADMIN_BOOTSTRAP_EMAIL/PASSWORD are declared optional here
(not required) because architecture 6.3 / PRD FR-1 AC3 says the app must
still start and log a warning, not crash, when they're absent.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://dev:dev@db:5432/trading_tom_v2"
    jwt_secret: str = "dev-secret-change-me"

    admin_bootstrap_email: str | None = None
    admin_bootstrap_password: str | None = None

    market_data_api_key: str | None = None

    # Guards app.scheduler.start_scheduler() from running during tests/
    # import (architecture 2.4 "single Uvicorn process" + this slice's
    # task note "guard so it doesn't start during tests"). Defaults True
    # (real deployments want the scheduler); test fixtures/conftest can
    # override via the ENABLE_SCHEDULER env var, but the simpler and
    # more robust guard actually used in app.main is "are we running
    # under pytest" (see app/main.py), this flag is a secondary manual
    # override for local debugging (e.g. running uvicorn directly without
    # wanting the cron to fire).
    enable_scheduler: bool = True


# Module-level singleton. Reading env vars here is safe at import time
# (no I/O, no DB connection) — actual DB connections are deferred to
# db.py's engine creation, which happens lazily.
settings = Settings()
