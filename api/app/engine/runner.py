"""Engine apply layer + orchestrator (architecture Section 4.1 pseudocode,
Section 4.4 fills, Section 7.2 trade cycle; PRD Section 4).

`run_engine()` is the single entrypoint used by both the scheduler
(app/scheduler.py) and, later, the manual-trigger API route. It is also
the function a future backtest slice will call per simulated day with a
single in-memory virtual account instead of real `accounts` rows
(architecture 4.6) — the apply-layer functions below take plain values
(price, cash, positions) wherever possible so that reuse is mechanical.

Transaction model (architecture 4.4 "All of (1)-(4) for a single account
happen in ONE DB transaction", Section 7.2 step 4): each account's exits
+ entries + equity recompute commit together. A failure for one account
(e.g. a DB error) only rolls back that account's work; previously
committed accounts in the same run stand, matching architecture 7.2's
"already-committed per-account transactions stand" resumability note.
Per-ticker market-data fetch failures are caught at the signal layer
(once, before any account is touched), logged, and recorded in
engine_runs.errors — that ticker is simply absent from `indicator_sets`
for the rest of the run, so no account-level code needs to know about it.
"""

import datetime
import decimal
import logging
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import strategy_config
from app.engine.signals import (
    ENTRY_TREND_MOMENTUM,
    IndicatorSet,
    compute_indicator_set,
    check_exit,
    entry_signals,
)
from app.market_data import MarketDataFetchError, MarketDataProvider, get_daily_bars
from app.models import Account, EngineRun, Position, Trade, User

logger = logging.getLogger(__name__)

# Generous calendar-day lookback so the bar window comfortably covers the
# slowest indicator window (SMA50) plus weekends/holidays/the one extra
# prior bar crossover detection needs.
LOOKBACK_CALENDAR_DAYS = strategy_config.SMA_TREND_SLOW * 3


def _build_indicator_sets(
    db: Session,
    as_of_date: datetime.date,
    universe: list[str],
    errors: list[dict],
    provider: MarketDataProvider | None = None,
) -> dict[str, IndicatorSet]:
    """Signal layer step 1 (architecture 7.2 step 3a/3b): fetch bars for
    every universe ticker (cache-first), compute indicators, and return a
    {ticker: IndicatorSet} map. A ticker is silently absent from the
    returned map (not raised) if its fetch fails or it lacks enough
    history — the caller (run_engine) treats "no entry for this ticker"
    as "skip it this run," matching PRD 7.3 "log, skip, run stays
    complete."

    `provider` defaults to None (get_daily_bars falls back to
    YFinanceProvider); tests pass a fake provider so no real network
    call happens.
    """
    indicator_sets: dict[str, IndicatorSet] = {}
    for ticker in universe:
        try:
            bars = get_daily_bars(db, ticker, LOOKBACK_CALENDAR_DAYS, as_of_date, provider=provider)
        except MarketDataFetchError as exc:
            logger.warning("market data fetch failed for %s: %s", ticker, exc)
            errors.append({"ticker": ticker, "error": str(exc)})
            continue

        indicator_set = compute_indicator_set(bars)
        if indicator_set is None:
            logger.info("insufficient history for %s, skipping this run", ticker)
            continue

        indicator_sets[ticker] = indicator_set

    return indicator_sets


def _trading_days_held(
    db: Session, ticker: str, entry_date: datetime.date, as_of_date: datetime.date
) -> int:
    """Number of trading days elapsed since entry, counted from the
    cached daily bars for this ticker (architecture 4.5 "10-trading-day
    max hold"). Counts bars strictly after entry_date through as_of_date
    inclusive, so a position entered "today" has 0 days held today and
    reaches the 10-day cap on the 10th subsequent bar.
    """
    from app.models import MarketDataCache

    count = db.execute(
        select(MarketDataCache.bar_date).where(
            MarketDataCache.ticker == ticker,
            MarketDataCache.bar_date > entry_date,
            MarketDataCache.bar_date <= as_of_date,
        )
    ).scalars().all()
    return len(count)


def _process_exits(
    db: Session,
    account: Account,
    indicator_sets: dict[str, IndicatorSet],
    engine_run_id: int,
    as_of_date: datetime.date,
) -> int:
    """Exits first (architecture 4.1 step 1, PRD 4.6 step 2) so cash/slots
    free up before entries are considered for this same account/run.
    Returns the number of SELL trades executed.
    """
    positions = db.execute(
        select(Position).where(Position.user_id == account.user_id)
    ).scalars().all()

    sells = 0
    for position in positions:
        indicator_set = indicator_sets.get(position.ticker)
        if indicator_set is None:
            # No fresh data for this ticker this run (fetch failure or
            # insufficient history) — leave the position untouched rather
            # than guessing at a price (architecture 7.2 "skip ticker").
            continue

        days_held = _trading_days_held(db, position.ticker, position.entry_date, as_of_date)
        reason = check_exit(
            entry_price=float(position.entry_price),
            entry_date=position.entry_date,
            indicator_set=indicator_set,
            as_of_date=as_of_date,
            trading_days_held=days_held,
        )
        if reason is None:
            continue

        price = decimal.Decimal(str(indicator_set.close))
        proceeds = price * position.quantity
        cost_basis = position.entry_price * position.quantity
        realized_pnl = proceeds - cost_basis

        db.add(
            Trade(
                user_id=account.user_id,
                ticker=position.ticker,
                side="SELL",
                quantity=position.quantity,
                price=price,
                trade_value=proceeds,
                bar_date=as_of_date,
                signal_reason=reason,
                realized_pnl=realized_pnl,
                position_id=position.id,
                engine_run_id=engine_run_id,
            )
        )
        account.cash_balance = account.cash_balance + proceeds
        account.realized_pnl = account.realized_pnl + realized_pnl
        db.delete(position)
        sells += 1

    db.flush()
    return sells


def _process_entries(
    db: Session,
    account: Account,
    signals: list,
    engine_run_id: int,
    as_of_date: datetime.date,
) -> int:
    """Entries (architecture 4.1 step 2, PRD 4.4): size = floor(cash * 10%
    / close), max 5 concurrent positions, skip duplicate ticker /
    insufficient cash / slot cap. Returns the number of BUY trades
    executed.
    """
    open_tickers = {
        row[0]
        for row in db.execute(
            select(Position.ticker).where(Position.user_id == account.user_id)
        ).all()
    }
    open_count = len(open_tickers)

    buys = 0
    for signal in signals:
        if open_count >= strategy_config.MAX_CONCURRENT_POSITIONS:
            break
        if signal.ticker in open_tickers:
            continue

        price = decimal.Decimal(str(signal.price))
        if price <= 0:
            continue

        budget = account.cash_balance * decimal.Decimal(str(strategy_config.POSITION_SIZE_PCT))
        quantity = math.floor(budget / price)
        if quantity <= 0:
            continue

        cost = price * quantity
        if cost > account.cash_balance:
            continue

        trade = Trade(
            user_id=account.user_id,
            ticker=signal.ticker,
            side="BUY",
            quantity=quantity,
            price=price,
            trade_value=cost,
            bar_date=as_of_date,
            signal_reason=signal.reason,
            realized_pnl=None,
            position_id=None,
            engine_run_id=engine_run_id,
        )
        db.add(trade)
        db.flush()  # populate trade.id for the Position FK below

        db.add(
            Position(
                user_id=account.user_id,
                ticker=signal.ticker,
                quantity=quantity,
                entry_price=price,
                entry_date=as_of_date,
                entry_trade_id=trade.id,
                last_mark_price=price,
            )
        )
        account.cash_balance = account.cash_balance - cost
        open_tickers.add(signal.ticker)
        open_count += 1
        buys += 1

    db.flush()
    return buys


def _recompute_equity_value(
    db: Session, account: Account, indicator_sets: dict[str, IndicatorSet]
) -> None:
    """After exits+entries, recompute equity_value from latest marks
    (architecture 4.4 step 4, 7.2 step 4c). Positions whose ticker had no
    fresh data this run keep their previous last_mark_price (stale-mark
    fallback — architecture design 4.2 "stale-data banner using
    last-known marks").
    """
    positions = db.execute(
        select(Position).where(Position.user_id == account.user_id)
    ).scalars().all()

    equity = decimal.Decimal("0")
    for position in positions:
        indicator_set = indicator_sets.get(position.ticker)
        if indicator_set is not None:
            position.last_mark_price = decimal.Decimal(str(indicator_set.close))
        mark = position.last_mark_price if position.last_mark_price is not None else position.entry_price
        equity += mark * position.quantity

    account.equity_value = equity


def active_accounts(db: Session) -> list[Account]:
    """Accounts eligible for this run (architecture 4.2 / PRD 3.3):
    is_active AND cash_balance + equity_value > 0. Funding *is*
    activation — there is no separate toggle.
    """
    accounts = (
        db.execute(select(Account).join(User, Account.user_id == User.id).where(User.is_active.is_(True)))
        .scalars()
        .all()
    )
    return [a for a in accounts if (a.cash_balance + a.equity_value) > 0]


def run_engine(
    db: Session,
    engine_run_id: int,
    as_of_date: datetime.date,
    accounts: list[Account] | None = None,
    universe: list[str] | None = None,
    provider: MarketDataProvider | None = None,
) -> dict:
    """Architecture 4.1 pseudocode, executed for real:

      1. SIGNAL LAYER (once): fetch bars, compute indicators, compute
         entry signals for the whole universe.
      2. APPLY LAYER (per eligible account, one DB transaction each):
         exits first, then entries, then recompute equity_value.
      3. Return a summary dict the caller (scheduler) uses to finalize
         the engine_runs row.

    `accounts` defaults to `active_accounts(db)` (architecture 4.2); a
    future backtest path can pass a single synthetic virtual account
    instead (architecture 4.6) and reuse everything else unchanged.
    `universe` defaults to strategy_config.UNIVERSE. `provider` defaults
    to the adapter's own default (YFinanceProvider); tests pass a fake
    provider to avoid any real network call.
    """
    universe = universe if universe is not None else strategy_config.UNIVERSE
    accounts = accounts if accounts is not None else active_accounts(db)

    errors: list[dict] = []
    indicator_sets = _build_indicator_sets(db, as_of_date, universe, errors, provider=provider)
    db.commit()  # persist any newly-cached market data rows independent of account txns

    buy_signals = entry_signals(list(indicator_sets.values()))

    trades_executed = 0
    users_affected = 0

    for account in accounts:
        try:
            sells = _process_exits(db, account, indicator_sets, engine_run_id, as_of_date)
            buys = _process_entries(db, account, buy_signals, engine_run_id, as_of_date)
            _recompute_equity_value(db, account, indicator_sets)
            db.commit()
        except Exception:
            # One account's failure rolls back only that account's
            # in-flight transaction; already-committed accounts in this
            # run stand (architecture 7.2 closing paragraph).
            db.rollback()
            logger.exception("engine run %s: account %s failed, rolled back", engine_run_id, account.user_id)
            errors.append({"user_id": account.user_id, "error": "account processing failed"})
            continue

        if sells or buys:
            trades_executed += sells + buys
            users_affected += 1

    return {
        "tickers_evaluated": len(universe),
        "signals_fired": len(buy_signals),
        "trades_executed": trades_executed,
        "users_affected": users_affected,
        "errors": errors,
    }
