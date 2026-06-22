"""Pure, user-independent signal layer (architecture Section 4.1 "SIGNAL
LAYER", 4.3 entry logic, 4.5 exit logic; PRD 4.3, 4.5).

Nothing here touches a DB session, a user, or an account — these
functions take indicator values / bars and return decisions. This is
what architecture 4.7 / PRD 4.7 means by "signals are computed once per
run, then applied across every user" and what 4.6 means by "the backtest
reuses the exact same signal-evaluation and exit-rule code path."

Two entry points:
  - entry_signals(indicator_sets) -> list[Signal]   (BUY decisions)
  - check_exit(position, indicator_set, as_of_date) -> str | None (EXIT_* reason)
"""

import dataclasses
import datetime

from app import strategy_config
from app.indicators import ema_series, rsi, sma_series
from app.market_data import Bar

ENTRY_TREND_MOMENTUM = "ENTRY_TREND_MOMENTUM"
EXIT_PROFIT_TARGET = "EXIT_PROFIT_TARGET"
EXIT_STOP_LOSS = "EXIT_STOP_LOSS"
EXIT_MAX_HOLD = "EXIT_MAX_HOLD"
EXIT_TREND_INVALIDATION = "EXIT_TREND_INVALIDATION"


@dataclasses.dataclass
class IndicatorSet:
    """Computed indicators for one ticker as of its latest bar, plus just
    enough series history to detect crossovers (architecture 4.3 condition
    3: "crossed... in the last 1 trading day" needs today's AND
    yesterday's indicator values).

    `bars` is the oldest-first list of daily Bar objects the indicators
    were computed from; `close` is the latest (as-of) bar's close, used
    as the fill price for both entries and exits (PRD 5.1).
    """

    ticker: str
    bar_date: datetime.date
    close: float
    sma_fast: float | None  # SMA20
    sma_slow: float | None  # SMA50
    sma_fast_prev: float | None
    sma_slow_prev: float | None
    ema_trigger: float | None  # EMA10
    ema_trigger_prev: float | None
    rsi_value: float | None


def compute_indicator_set(bars: list[Bar]) -> IndicatorSet | None:
    """Build an IndicatorSet from oldest-first daily bars. Returns None if
    there isn't enough history for the slowest window (SMA50) plus one
    prior bar (needed for crossover detection) — the caller treats this
    ticker as having no signal this run rather than crashing.
    """
    if len(bars) < strategy_config.SMA_TREND_SLOW + 1:
        return None

    closes = [float(b.close) for b in bars]

    sma_fast_series = sma_series(closes, strategy_config.SMA_TREND_FAST)
    sma_slow_series = sma_series(closes, strategy_config.SMA_TREND_SLOW)
    ema_trigger_series = ema_series(closes, strategy_config.EMA_TRIGGER_PERIOD)

    return IndicatorSet(
        ticker=bars[-1].ticker,
        bar_date=bars[-1].bar_date,
        close=closes[-1],
        sma_fast=sma_fast_series[-1],
        sma_slow=sma_slow_series[-1],
        sma_fast_prev=sma_fast_series[-2],
        sma_slow_prev=sma_slow_series[-2],
        ema_trigger=ema_trigger_series[-1],
        ema_trigger_prev=ema_trigger_series[-2],
        rsi_value=rsi(closes, strategy_config.RSI_PERIOD),
    )


@dataclasses.dataclass
class Signal:
    """A BUY decision for one ticker, produced once per run and applied
    identically to every eligible account (architecture 4.7).
    """

    ticker: str
    bar_date: datetime.date
    price: float
    reason: str = ENTRY_TREND_MOMENTUM


def _crossed_above(prev_a: float | None, prev_b: float | None, a: float | None, b: float | None) -> bool:
    """True if series `a` was <= series `b` on the prior bar and is now > b
    (a same-bar bullish crossover). Conservative: any missing value means
    "no crossover" rather than guessing.
    """
    if prev_a is None or prev_b is None or a is None or b is None:
        return False
    return prev_a <= prev_b and a > b


def _crossed_below(prev_a: float | None, prev_b: float | None, a: float | None, b: float | None) -> bool:
    if prev_a is None or prev_b is None or a is None or b is None:
        return False
    return prev_a >= prev_b and a < b


def entry_signals(indicator_sets: list[IndicatorSet]) -> list[Signal]:
    """BUY signal per ticker where all three entry conditions hold on the
    same run (architecture 4.3 / PRD 4.3):
      1. SMA20 > SMA50 (trend filter)
      2. RSI14 in [50, 70] (momentum, not overbought)
      3. EMA10 crossed above SMA20 in the last bar (trigger)
    """
    signals = []
    for ind in indicator_sets:
        if ind.sma_fast is None or ind.sma_slow is None or ind.rsi_value is None:
            continue

        trend_filter = ind.sma_fast > ind.sma_slow
        momentum_ok = strategy_config.RSI_BAND_LOW <= ind.rsi_value <= strategy_config.RSI_BAND_HIGH
        trigger = _crossed_above(
            ind.ema_trigger_prev, ind.sma_fast_prev, ind.ema_trigger, ind.sma_fast
        )

        if trend_filter and momentum_ok and trigger:
            signals.append(
                Signal(
                    ticker=ind.ticker,
                    bar_date=ind.bar_date,
                    price=ind.close,
                    reason=ENTRY_TREND_MOMENTUM,
                )
            )
    return signals


def check_exit(
    entry_price: float,
    entry_date: datetime.date,
    indicator_set: IndicatorSet,
    as_of_date: datetime.date,
    trading_days_held: int,
) -> str | None:
    """First-to-trigger exit reason for one open position (architecture
    4.5 / PRD 4.5), checked in the order the PRD lists them:
      1. +8% profit target
      2. -4% stop loss
      3. 10-trading-day max hold
      4. SMA20 crosses below SMA50 (trend invalidation)

    `trading_days_held` is the number of trading days (bars) since entry,
    supplied by the caller (the apply layer knows the run cadence); this
    function does no date-arithmetic itself so backtests (which iterate
    bar-by-bar) and the live engine (one bar per run) compute "how many
    trading days held" identically without duplicating that logic here.

    Returns None if no exit condition is met (position stays open).
    """
    price = indicator_set.close

    pct_change = (price - entry_price) / entry_price
    if pct_change >= strategy_config.PROFIT_TARGET_PCT:
        return EXIT_PROFIT_TARGET

    if pct_change <= -strategy_config.STOP_LOSS_PCT:
        return EXIT_STOP_LOSS

    if trading_days_held >= strategy_config.MAX_HOLD_TRADING_DAYS:
        return EXIT_MAX_HOLD

    if _crossed_below(
        indicator_set.sma_fast_prev,
        indicator_set.sma_slow_prev,
        indicator_set.sma_fast,
        indicator_set.sma_slow,
    ):
        return EXIT_TREND_INVALIDATION

    return None
