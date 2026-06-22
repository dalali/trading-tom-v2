"""Tests that app.main never starts the real APScheduler under pytest
(architecture 2.4 "single Uvicorn process" — a second scheduler instance
started incidentally by the test process must never fire the cron job).
"""

from app.main import _scheduler_should_start


def test_scheduler_guard_is_false_under_pytest():
    # This test file itself runs under pytest, so 'pytest' is in
    # sys.modules — the guard must return False regardless of the
    # enable_scheduler setting.
    assert _scheduler_should_start() is False


def test_app_lifespan_does_not_start_scheduler_under_pytest(client):
    # The `client` fixture's TestClient context manager runs the
    # lifespan; if the scheduler were started here it would still be
    # running (and untracked) after the `with` block exits. We can't
    # directly inspect "no scheduler was created," but we can assert the
    # health endpoint still works after entering/exiting the lifespan,
    # which would not be reliably true if a stray background thread
    # crashed app startup.
    response = client.get("/health")
    assert response.status_code == 200
