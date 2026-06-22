"""Tests for app/scheduler.py: single-flight rejection, run finalization,
and status reporting. No real Postgres/advisory lock involved — the
sqlite test DB exercises the engine_runs-row check, which is the primary,
portable single-flight guard (architecture 2.4/3.2; the Postgres advisory
lock is an additional cross-process safety net not exercisable here).
"""

import datetime
import decimal

import pytest

from app.models import Account, EngineRun, User
from app.scheduler import (
    EngineRunInProgress,
    execute_run,
    get_engine_status,
    is_run_in_progress,
    trigger_manual_run,
)

AS_OF = datetime.date(2024, 6, 3)


def _make_funded_user(db):
    user = User(
        email="sched@example.com",
        email_lower="sched@example.com",
        display_name="Sched",
        password_hash="x",
        role="user",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(Account(user_id=user.id, cash_balance=decimal.Decimal("10000")))
    db.commit()


def test_is_run_in_progress_false_when_no_runs(db_session_with_engine_runs):
    assert is_run_in_progress(db_session_with_engine_runs) is False


def test_is_run_in_progress_true_when_a_run_is_running(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    db.add(EngineRun(trigger="manual", status="running"))
    db.commit()
    assert is_run_in_progress(db) is True


def test_execute_run_rejects_concurrent_run(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    db.add(EngineRun(trigger="scheduled", status="running"))
    db.commit()

    with pytest.raises(EngineRunInProgress):
        execute_run(db, trigger="manual", as_of_date=AS_OF)


def test_trigger_manual_run_rejects_when_already_running(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    db.add(EngineRun(trigger="scheduled", status="running"))
    db.commit()

    with pytest.raises(EngineRunInProgress):
        trigger_manual_run(db, as_of_date=AS_OF)


def test_execute_run_completes_and_finalizes_summary(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    _make_funded_user(db)

    # Empty universe -> nothing to fetch, run completes trivially with a
    # clean summary (no real market data / network dependency needed
    # here; the run_engine() path itself is covered by
    # tests/test_engine_runner.py).
    run = execute_run(db, trigger="manual", as_of_date=AS_OF, universe=[])

    assert run.status == "complete"
    assert run.finished_at is not None
    assert run.tickers_evaluated == 0
    assert run.errors == []


def test_execute_run_releases_lock_so_a_subsequent_run_can_proceed(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    _make_funded_user(db)

    first = execute_run(db, trigger="manual", as_of_date=AS_OF, universe=[])
    assert first.status == "complete"

    # Now that the first run finished (status != 'running'), a second
    # run must be allowed to start.
    second = execute_run(db, trigger="manual", as_of_date=AS_OF, universe=[])
    assert second.status == "complete"
    assert second.id != first.id


def test_get_engine_status_reports_idle_with_no_runs(db_session_with_engine_runs):
    status = get_engine_status(db_session_with_engine_runs)
    assert status["state"] == "idle"
    assert status["last_run"] is None


def test_get_engine_status_reports_running(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    db.add(EngineRun(trigger="scheduled", status="running"))
    db.commit()

    status = get_engine_status(db)
    assert status["state"] == "running"
    assert status["last_run"] is not None


def test_get_engine_status_reports_idle_with_last_completed_run(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    _make_funded_user(db)
    execute_run(db, trigger="manual", as_of_date=AS_OF, universe=[])

    status = get_engine_status(db)
    assert status["state"] == "idle"
    assert status["last_run"].status == "complete"
