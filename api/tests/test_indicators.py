"""Unit tests for app/indicators.py against known hand-computed values."""

from app.indicators import ema, rsi, sma, sma_series


def test_sma_known_value():
    closes = [1, 2, 3, 4, 5]
    assert sma(closes, 5) == 3.0


def test_sma_uses_last_n_values_only():
    closes = [100, 100, 100, 1, 2, 3]
    assert sma(closes, 3) == 2.0


def test_sma_insufficient_history_returns_none():
    assert sma([1, 2], 5) is None


def test_sma_series_has_none_until_window_filled():
    closes = [1, 2, 3, 4, 5]
    series = sma_series(closes, 3)
    assert series[0] is None
    assert series[1] is None
    assert series[2] == 2.0
    assert series[3] == 3.0
    assert series[4] == 4.0


def test_ema_seeds_with_sma_then_smooths():
    # period=3, multiplier = 2/4 = 0.5
    closes = [1, 2, 3, 10]
    # seed = sma(1,2,3) = 2.0
    # next = (10 - 2.0) * 0.5 + 2.0 = 6.0
    assert ema(closes, 3) == 6.0


def test_ema_insufficient_history_returns_none():
    assert ema([1, 2], 5) is None


def test_ema_constant_series_equals_the_constant():
    closes = [5.0] * 10
    assert ema(closes, 5) == 5.0


def test_rsi_all_gains_is_100():
    closes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    assert rsi(closes, 14) == 100.0


def test_rsi_all_losses_is_0():
    closes = list(range(15, 0, -1))
    assert rsi(closes, 14) == 0.0


def test_rsi_known_value_wilder_example():
    # Classic alternating-gain/loss series, period=14, hand-checkable:
    # equal up/down moves of the same magnitude -> RSI settles at 50.
    closes = [100]
    for i in range(20):
        closes.append(closes[-1] + (1 if i % 2 == 0 else -1))
    value = rsi(closes, 14)
    assert value is not None
    assert 45 <= value <= 55


def test_rsi_insufficient_history_returns_none():
    assert rsi([1, 2, 3], 14) is None
