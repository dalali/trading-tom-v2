"""Login throttle tests (architecture 6.4)."""

import importlib

import app.throttle as throttle_module


def _fresh_throttle(monkeypatch):
    """Reload the module so each test starts with empty failure state,
    since _failures is a module-level dict shared across tests.
    """
    importlib.reload(throttle_module)
    return throttle_module


def test_not_locked_before_any_failures(monkeypatch):
    throttle = _fresh_throttle(monkeypatch)

    assert throttle.check_locked("1.2.3.4", "a@example.com") is False


def test_locks_out_after_max_failures(monkeypatch):
    throttle = _fresh_throttle(monkeypatch)

    for _ in range(throttle.MAX_FAILURES):
        throttle.record_failure("1.2.3.4", "a@example.com")

    assert throttle.check_locked("1.2.3.4", "a@example.com") is True


def test_not_locked_below_max_failures(monkeypatch):
    throttle = _fresh_throttle(monkeypatch)

    for _ in range(throttle.MAX_FAILURES - 1):
        throttle.record_failure("1.2.3.4", "a@example.com")

    assert throttle.check_locked("1.2.3.4", "a@example.com") is False


def test_record_success_clears_failures(monkeypatch):
    throttle = _fresh_throttle(monkeypatch)

    for _ in range(throttle.MAX_FAILURES):
        throttle.record_failure("1.2.3.4", "a@example.com")
    throttle.record_success("1.2.3.4", "a@example.com")

    assert throttle.check_locked("1.2.3.4", "a@example.com") is False


def test_lockout_is_independent_per_key(monkeypatch):
    throttle = _fresh_throttle(monkeypatch)

    for _ in range(throttle.MAX_FAILURES):
        throttle.record_failure("1.2.3.4", "a@example.com")

    # A different IP/email pair is unaffected.
    assert throttle.check_locked("9.9.9.9", "b@example.com") is False


def test_cooldown_window_expires(monkeypatch):
    throttle = _fresh_throttle(monkeypatch)

    fake_now = [1000.0]
    monkeypatch.setattr(throttle.time, "monotonic", lambda: fake_now[0])

    for _ in range(throttle.MAX_FAILURES):
        throttle.record_failure("1.2.3.4", "a@example.com")
    assert throttle.check_locked("1.2.3.4", "a@example.com") is True

    fake_now[0] += throttle.COOLDOWN_SECONDS + 1

    assert throttle.check_locked("1.2.3.4", "a@example.com") is False
