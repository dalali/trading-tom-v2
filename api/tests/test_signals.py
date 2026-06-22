"""Tests for app/engine/signals.py: entry signal gating and each exit
reason, using deterministic synthetic price series (no DB, no network).
"""

import datetime

from app.engine.signals import (
    EXIT_MAX_HOLD,
    EXIT_PROFIT_TARGET,
    EXIT_STOP_LOSS,
    EXIT_TREND_INVALIDATION,
    IndicatorSet,
    Signal,
    check_exit,
    compute_indicator_set,
    entry_signals,
)
from app.market_data import Bar


def _bars(ticker, closes, start_date=datetime.date(2024, 1, 1)):
    bars = []
    d = start_date
    for c in closes:
        bars.append(Bar(ticker=ticker, bar_date=d, open=c, high=c, low=c, close=c, volume=1))
        d += datetime.timedelta(days=1)
    return bars


def _ind(**overrides):
    base = dict(
        ticker="TST",
        bar_date=datetime.date(2024, 6, 1),
        close=100.0,
        sma_fast=20.0,
        sma_slow=10.0,
        sma_fast_prev=20.0,
        sma_slow_prev=10.0,
        ema_trigger=20.0,
        ema_trigger_prev=20.0,
        rsi_value=60.0,
    )
    base.update(overrides)
    return IndicatorSet(**base)


# --- entry_signals ---------------------------------------------------


def test_entry_fires_when_all_three_conditions_hold():
    ind = _ind(
        sma_fast=20.0,
        sma_slow=15.0,  # trend filter: fast > slow
        rsi_value=60.0,  # momentum: in [50,70]
        ema_trigger_prev=14.0,
        sma_fast_prev=15.0,  # prev: ema <= sma_fast
        ema_trigger=21.0,
        # now: ema > sma_fast -> crossed above
    )
    signals = entry_signals([ind])
    assert len(signals) == 1
    assert signals[0].ticker == "TST"
    assert signals[0].reason == "ENTRY_TREND_MOMENTUM"
    assert signals[0].price == 100.0


def test_entry_skipped_without_trend_filter():
    ind = _ind(
        sma_fast=10.0,
        sma_slow=20.0,  # fast < slow: no uptrend
        rsi_value=60.0,
        ema_trigger_prev=9.0,
        sma_fast_prev=10.0,
        ema_trigger=11.0,
    )
    assert entry_signals([ind]) == []


def test_entry_skipped_when_rsi_overbought():
    ind = _ind(
        sma_fast=20.0,
        sma_slow=15.0,
        rsi_value=75.0,  # > 70, overbought, excluded
        ema_trigger_prev=14.0,
        sma_fast_prev=15.0,
        ema_trigger=21.0,
    )
    assert entry_signals([ind]) == []


def test_entry_skipped_when_rsi_below_band():
    ind = _ind(
        sma_fast=20.0,
        sma_slow=15.0,
        rsi_value=40.0,  # < 50
        ema_trigger_prev=14.0,
        sma_fast_prev=15.0,
        ema_trigger=21.0,
    )
    assert entry_signals([ind]) == []


def test_entry_skipped_without_fresh_crossover():
    # EMA was already above SMA fast on the prior bar too -> stale, not fresh.
    ind = _ind(
        sma_fast=20.0,
        sma_slow=15.0,
        rsi_value=60.0,
        ema_trigger_prev=22.0,
        sma_fast_prev=19.0,  # prev: ema already > sma_fast
        ema_trigger=23.0,
    )
    assert entry_signals([ind]) == []


def test_entry_skipped_when_indicators_missing():
    ind = _ind(sma_fast=None)
    assert entry_signals([ind]) == []


# --- compute_indicator_set (integration of indicators.py) ------------


def test_compute_indicator_set_returns_none_with_insufficient_bars():
    bars = _bars("TST", [100.0] * 10)  # fewer than SMA_TREND_SLOW(50) + 1
    assert compute_indicator_set(bars) is None


def test_compute_indicator_set_builds_from_bars():
    closes = [100.0 + i * 0.1 for i in range(60)]
    bars = _bars("TST", closes)
    ind = compute_indicator_set(bars)
    assert ind is not None
    assert ind.ticker == "TST"
    assert ind.close == closes[-1]
    assert ind.sma_fast is not None
    assert ind.sma_slow is not None
    assert ind.rsi_value is not None


# --- check_exit: first-to-trigger order -------------------------------


def test_exit_profit_target():
    ind = _ind(close=108.5)  # +8.5% from entry 100
    reason = check_exit(
        entry_price=100.0,
        entry_date=datetime.date(2024, 1, 1),
        indicator_set=ind,
        as_of_date=datetime.date(2024, 1, 5),
        trading_days_held=2,
    )
    assert reason == EXIT_PROFIT_TARGET


def test_exit_stop_loss():
    ind = _ind(close=95.5)  # -4.5% from entry 100
    reason = check_exit(
        entry_price=100.0,
        entry_date=datetime.date(2024, 1, 1),
        indicator_set=ind,
        as_of_date=datetime.date(2024, 1, 5),
        trading_days_held=2,
    )
    assert reason == EXIT_STOP_LOSS


def test_exit_max_hold():
    ind = _ind(close=101.0)  # within target/stop band
    reason = check_exit(
        entry_price=100.0,
        entry_date=datetime.date(2024, 1, 1),
        indicator_set=ind,
        as_of_date=datetime.date(2024, 1, 20),
        trading_days_held=10,
    )
    assert reason == EXIT_MAX_HOLD


def test_exit_trend_invalidation():
    ind = _ind(
        close=101.0,
        sma_fast=14.0,
        sma_slow=15.0,
        sma_fast_prev=16.0,
        sma_slow_prev=15.0,  # prev: fast > slow, now: fast < slow -> crossed below
    )
    reason = check_exit(
        entry_price=100.0,
        entry_date=datetime.date(2024, 1, 1),
        indicator_set=ind,
        as_of_date=datetime.date(2024, 1, 5),
        trading_days_held=3,
    )
    assert reason == EXIT_TREND_INVALIDATION


def test_exit_none_when_nothing_triggers():
    ind = _ind(close=101.0)
    reason = check_exit(
        entry_price=100.0,
        entry_date=datetime.date(2024, 1, 1),
        indicator_set=ind,
        as_of_date=datetime.date(2024, 1, 3),
        trading_days_held=2,
    )
    assert reason is None


def test_exit_profit_target_wins_over_max_hold_when_both_true():
    # Even at max-hold day count, profit target should be reported first
    # per the PRD's "whichever triggers first" priority order.
    ind = _ind(close=110.0)
    reason = check_exit(
        entry_price=100.0,
        entry_date=datetime.date(2024, 1, 1),
        indicator_set=ind,
        as_of_date=datetime.date(2024, 1, 20),
        trading_days_held=10,
    )
    assert reason == EXIT_PROFIT_TARGET


def test_exit_stop_loss_wins_over_trend_invalidation_when_both_true():
    ind = _ind(
        close=95.0,
        sma_fast=14.0,
        sma_slow=15.0,
        sma_fast_prev=16.0,
        sma_slow_prev=15.0,
    )
    reason = check_exit(
        entry_price=100.0,
        entry_date=datetime.date(2024, 1, 1),
        indicator_set=ind,
        as_of_date=datetime.date(2024, 1, 5),
        trading_days_held=3,
    )
    assert reason == EXIT_STOP_LOSS
