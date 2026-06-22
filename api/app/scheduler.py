"""Single-flight engine-run trigger + APScheduler wiring (architecture
Section 2.4, 4.5, 7.2; PRD 4.6, FR-6).

Two layers of single-flight protection, per architecture 2.4 point 1 and
3.2's engine_runs note ("a single status='running' row + a Postgres
advisory lock is the single-flight mechanism"):
  1. The `engine_runs` row itself — `is_run_in_progress()` checks for any
     row in status='running'. This is the primary, portable check (it
     works the same on Postgres and the sqlite test DB) and is what
     FR-6 AC2's "manual trigger rejected if a run is already in
     progress" is built on.
  2. A Postgres advisory lock (`pg_try_advisory_lock`) as the
     belt-and-suspenders cross-process safety net for the rare case
     where two processes race past check (1) at the same instant
     (architecture 2.4 point 2's "the advisory-lock single-flight rule
     is the safety net even if [multiple workers are] misconfigured").
     This is a no-op on sqlite (no advisory locks there), which is fine
     since tests only run a single process anyway.

`trigger_manual_run()` and `run_scheduled()` are the two callers of
`execute_run()`; both go through the same single-flight gate and the
same `run_engine()` code path (PRD FR-6 AC1: "identical code path as the
scheduled run").

The next slice's `/admin/engine/run` POST route wraps `trigger_manual_run`
directly (raises EngineRunInProgress -> that route translates it to a
409, per architecture 5.5 / FR-6 AC2). Not built here.
"""

import datetime
import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.engine.runner import run_engine
from app.models import EngineRun

logger = logging.getLogger(__name__)

# Arbitrary fixed key for the single engine-run advisory lock (architecture
# 2.4). Any consistent int64 works; this one has no special meaning.
ADVISORY_LOCK_KEY = 8675309


class EngineRunInProgress(Exception):
    """Raised when a run is requested while another is already running
    (architecture 7.2 step 2 "manual trigger meanwhile -> 409").
    """


def is_run_in_progress(db: Session) -> bool:
    """True if any engine_runs row is currently status='running'."""
    existing = db.execute(select(EngineRun).where(EngineRun.status == "running")).first()
    return existing is not None


def _try_acquire_advisory_lock(db: Session) -> bool:
    """Best-effort Postgres advisory lock. Returns True if acquired (or if
    running on a backend without advisory-lock support, e.g. sqlite in
    tests, in which case the engine_runs-row check above is the sole
    guard). Never raises.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    result = db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY})
    return bool(result.scalar())


def _release_advisory_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": ADVISORY_LOCK_KEY})


def execute_run(
    db: Session,
    trigger: str,
    as_of_date: datetime.date | None = None,
    universe: list[str] | None = None,
    provider=None,
) -> EngineRun:
    """Create the engine_runs row, take the single-flight lock, run the
    engine, and finalize the summary (architecture 7.2 steps 1-6).

    Raises EngineRunInProgress (caller maps to 409) if a run is already
    in progress. `trigger` is 'scheduled' or 'manual' (architecture
    4.5/PRD FR-6 AC1 — both call this same function). `universe`/
    `provider` default to run_engine()'s own defaults (the full
    strategy_config.UNIVERSE and YFinanceProvider); tests pass overrides
    to avoid any real network call.
    """
    as_of_date = as_of_date or datetime.date.today()

    if is_run_in_progress(db):
        raise EngineRunInProgress("An engine run is already in progress")

    if not _try_acquire_advisory_lock(db):
        raise EngineRunInProgress("An engine run is already in progress")

    engine_run = EngineRun(trigger=trigger, status="running")
    db.add(engine_run)
    db.commit()

    try:
        summary = run_engine(db, engine_run.id, as_of_date, universe=universe, provider=provider)
        engine_run.status = "complete"
        engine_run.tickers_evaluated = summary["tickers_evaluated"]
        engine_run.signals_fired = summary["signals_fired"]
        engine_run.trades_executed = summary["trades_executed"]
        engine_run.users_affected = summary["users_affected"]
        engine_run.errors = summary["errors"]
    except Exception:
        logger.exception("engine run %s failed", engine_run.id)
        engine_run.status = "failed"
        engine_run.errors = [*(engine_run.errors or []), {"error": "engine run raised an exception"}]
    finally:
        engine_run.finished_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
        _release_advisory_lock(db)

    return engine_run


def trigger_manual_run(db: Session, as_of_date: datetime.date | None = None) -> EngineRun:
    """Admin "trigger run now" entrypoint (architecture 4.5, PRD FR-6
    AC1). The next slice's POST /admin/engine/run route calls this and
    translates EngineRunInProgress into a 409 (FR-6 AC2).
    """
    return execute_run(db, trigger="manual", as_of_date=as_of_date)


def get_engine_status(db: Session) -> dict:
    """Data for the next slice's GET /admin/engine/status route
    (architecture 5.5): current state + most recent run. Kept here, not
    in a router, since this slice doesn't build the HTTP layer.
    """
    running = is_run_in_progress(db)
    last_run = db.execute(select(EngineRun).order_by(EngineRun.started_at.desc())).scalars().first()
    return {
        "state": "running" if running else "idle",
        "last_run": last_run,
    }


def _run_scheduled_job() -> None:
    """The function APScheduler's cron trigger calls. Opens its own
    session (the scheduler runs on a background thread, separate from
    any request-scoped session) and always closes it.
    """
    db = SessionLocal()
    try:
        execute_run(db, trigger="scheduled")
    except EngineRunInProgress:
        logger.warning("Scheduled engine run skipped: a run is already in progress")
    finally:
        db.close()


def start_scheduler():
    """Build and start the APScheduler instance (architecture 2.4, 4.5):
    a daily cron job at 17:00 US/Eastern calling the engine.

    Returns the started BackgroundScheduler so the caller (app.main's
    lifespan) can shut it down on app shutdown. Import of apscheduler is
    deferred into this function so importing app.scheduler itself never
    requires apscheduler to be installed in a context that doesn't need
    it (e.g. a future slice's lightweight unit test).
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    from app import strategy_config

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _run_scheduled_job,
        trigger=CronTrigger(
            hour=strategy_config.ENGINE_SCHEDULE_HOUR,
            minute=strategy_config.ENGINE_SCHEDULE_MINUTE,
            timezone=strategy_config.ENGINE_SCHEDULE_TIMEZONE,
        ),
        id="daily_engine_run",
        # A misfired run (e.g. container was down at 17:00) is simply
        # skipped rather than catching up — there is no "make up a missed
        # day" requirement (PRD 4.6's manual trigger is the documented
        # recovery path for a missed scheduled run).
        misfire_grace_time=None,
    )
    scheduler.start()
    return scheduler
