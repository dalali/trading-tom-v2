"""Strategy + universe config constants (architecture Section 4.3, PRD Section 4).

These are backend config, not DB tables and not admin-editable in MVP
(architecture assumption 11 / PRD assumption 13). Both the live engine
and the backtest engine import these same constants so live/backtest
math is guaranteed to agree.
"""

# Tradable universe: ~20-28 liquid large-cap US tickers + broad ETFs
# (PRD 4.2 / architecture 3.2 note). Exact list is an implementation-time
# config decision (PRD assumption 3) — large, liquid S&P 500 names plus
# SPY/QQQ for broad market exposure.
UNIVERSE: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "HD", "PG", "MA", "XOM", "JNJ",
    "COST", "ABBV", "MRK", "AVGO", "PEP", "ADBE", "CRM", "NFLX",
    "SPY", "QQQ",
]

# Trend filter (entry condition 1, PRD 4.3.1)
SMA_TREND_FAST = 20
SMA_TREND_SLOW = 50

# Momentum confirmation (entry condition 2, PRD 4.3.2)
RSI_PERIOD = 14
RSI_BAND_LOW = 50
RSI_BAND_HIGH = 70

# Trigger: EMA crossover (entry condition 3, PRD 4.3.3)
EMA_TRIGGER_PERIOD = 10

# Position sizing (PRD 4.4)
POSITION_SIZE_PCT = 0.10  # 10% of cash_balance per position
MAX_CONCURRENT_POSITIONS = 5

# Exit rules (PRD 4.5) — first to trigger wins, checked every run
PROFIT_TARGET_PCT = 0.08   # +8% above entry -> sell
STOP_LOSS_PCT = 0.04       # -4% below entry -> sell
MAX_HOLD_TRADING_DAYS = 10  # ~2 calendar weeks

# Engine schedule (PRD 4.6 / architecture 4.5): daily cron after market
# close, 17:00 US/Eastern. APScheduler is configured with this timezone
# so DST transitions are handled correctly.
ENGINE_SCHEDULE_HOUR = 17
ENGINE_SCHEDULE_MINUTE = 0
ENGINE_SCHEDULE_TIMEZONE = "US/Eastern"
