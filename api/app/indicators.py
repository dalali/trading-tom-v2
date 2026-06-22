"""Pure technical-indicator functions (architecture Section 4.3, PRD 4.3).

Operate on plain lists of closes (oldest-first) so they're usable by both
the live engine (app/market_data.py bars) and the future backtest path
without any DB/session dependency. No external TA library — the math is
simple enough to implement directly and keeps this module trivially
unit-testable (per task requirements).

All functions return None when there isn't enough history yet for the
requested window, rather than raising, since the engine's signal layer
needs to skip-not-crash on a ticker with insufficient history (e.g. a
recently listed ticker or a short cache warm-up period).
"""


def sma(closes: list[float], period: int) -> float | None:
    """Simple moving average of the last `period` closes."""
    if period <= 0 or len(closes) < period:
        return None
    window = closes[-period:]
    return sum(window) / period


def sma_series(closes: list[float], period: int) -> list[float | None]:
    """SMA value as of each index in `closes` (None where insufficient history).

    Used to detect crossovers (e.g. "EMA10 crossed above SMA20 in the last
    bar"), which require comparing today's and yesterday's indicator values.
    """
    return [sma(closes[: i + 1], period) for i in range(len(closes))]


def ema(closes: list[float], period: int) -> float | None:
    """Exponential moving average of `closes` over `period`.

    Standard EMA: seeded with the SMA of the first `period` closes, then
    smoothed forward with multiplier 2/(period+1).
    """
    if period <= 0 or len(closes) < period:
        return None
    multiplier = 2 / (period + 1)
    ema_value = sum(closes[:period]) / period
    for close in closes[period:]:
        ema_value = (close - ema_value) * multiplier + ema_value
    return ema_value


def ema_series(closes: list[float], period: int) -> list[float | None]:
    """EMA value as of each index in `closes` (None where insufficient history)."""
    return [ema(closes[: i + 1], period) for i in range(len(closes))]


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Relative Strength Index using Wilder's smoothing over `period`.

    Needs `period + 1` closes (period deltas). Returns None if there isn't
    enough history. A flat series with zero average loss returns 100.0
    (the textbook RSI(0)=100 convention), avoiding a divide-by-zero.
    """
    if period <= 0 or len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    """RSI value as of each index in `closes` (None where insufficient history)."""
    return [rsi(closes[: i + 1], period) for i in range(len(closes))]
