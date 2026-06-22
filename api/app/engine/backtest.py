"""Backtest service (architecture Section 4.6, 5.6; PRD Section 6).

Reuses the exact signal/exit/sizing functions the live engine uses
(app/engine/signals.py's compute_indicator_set/entry_signals/check_exit,
and the same sizing math as app/engine/runner.py's _process_entries),
iterated day-by-day over cached historical bars for a single in-memory
virtual account, instead of running once "today" across real accounts
(architecture 4.6). Writes ONLY to backtest_runs/backtest_trades — never
to trades/positions/accounts (assumption 14 / architecture 3.2, 9.1).

Lifecycle (PRD 6.5): a backtest_runs row is created with status='queued'
by the router (synchronously, in the request), then `execute_backtest()`
runs on a background thread (FastAPI BackgroundTasks, matching how
app/scheduler.py already documents backtests reusing "APScheduler's
thread pool / FastAPI BackgroundTasks" — this slice picks BackgroundTasks
since there's no need for a second scheduler instance) and transitions
queued -> running -> complete|failed.
"""

import dataclasses
import datetime
import decimal
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import strategy_config
from app.db import SessionLocal
from app.engine.signals import (
    IndicatorSet,
    check_exit,
    compute_indicator_set,
    entry_signals,
)
from app.market_data import Bar, MarketDataFetchError, MarketDataProvider, get_daily_bars
from app.models import BacktestRun, BacktestTrade

logger = logging.getLogger(__name__)

# Same generous lookback the live engine uses (runner.py), so the first
# simulated day already has enough history for the slowest indicator
# (SMA50) plus one prior bar for crossover detection.
LOOKBACK_CALENDAR_DAYS = strategy_config.SMA_TREND_SLOW * 3


class BacktestValidationError(Exception):
    """Raised for request-shape problems the router maps to 400
    (architecture 5.6: end<=start, or out of provider range).
    """


@dataclasses.dataclass
class VirtualPosition:
    """One open holding in the virtual account (architecture 4.6 "seeds a
    single in-memory virtual account" — never an ORM Position row).
    """

    ticker: str
    quantity: int
    entry_price: decimal.Decimal
    entry_date: datetime.date
    entry_trading_days_index: int  # index into that ticker's bar list at entry


@dataclasses.dataclass
class VirtualAccount:
    """In-memory stand-in for a real Account (architecture 4.6), seeded
    with starting_capital. realized_pnl tracked for summary metrics.
    """

    cash: decimal.Decimal
    positions: dict[str, VirtualPosition] = dataclasses.field(default_factory=dict)
    realized_pnl: decimal.Decimal = decimal.Decimal("0")


def validate_date_range(
    db: Session,
    start_date: datetime.date,
    end_date: datetime.date,
    tickers: list[str],
    provider: MarketDataProvider | None = None,
) -> None:
    """Architecture 5.6: 400 if end<=start or out of provider range.

    "Out of provider range" is checked against the configured universe's
    available cached/fetchable history via get_market_data_range(); a
    request entirely outside that range is rejected up front rather than
    silently producing an empty backtest.
    """
    if end_date <= start_date:
        raise BacktestValidationError("end_date must be after start_date")

    earliest, latest = get_market_data_range(db, tickers, provider=provider)
    if earliest is None or latest is None:
        # No data available at all for these tickers; let the run proceed
        # and fail gracefully later only if explicitly desired — but per
        # PRD FR-7 AC2 ("out of provider range" rejected at submission)
        # an unknown range can't be validated, so we don't block here.
        return

    if end_date < earliest or start_date > latest:
        raise BacktestValidationError(
            f"Requested range [{start_date}, {end_date}] is outside the "
            f"available provider range [{earliest}, {latest}]"
        )


def get_market_data_range(
    db: Session,
    tickers: list[str] | None = None,
    provider: MarketDataProvider | None = None,
) -> tuple[datetime.date | None, datetime.date | None]:
    """Architecture 5.7 GET /admin/market-data/range: {earliest, latest}
    across the cached market_data_cache table (optionally scoped to a
    ticker subset). Does not hit the network — this reflects what's
    already cached, which is what the backtest form's "available data"
    hint needs (design 4.11); a cold cache simply reports None/None.
    """
    from app.models import MarketDataCache

    query = select(MarketDataCache.bar_date)
    if tickers:
        query = query.where(MarketDataCache.ticker.in_(tickers))

    dates = db.execute(query).scalars().all()
    if not dates:
        return None, None
    return min(dates), max(dates)


def _fetch_ticker_bars(
    db: Session,
    ticker: str,
    start_date: datetime.date,
    end_date: datetime.date,
    errors: list[dict],
    provider: MarketDataProvider | None = None,
) -> list[Bar]:
    """Bulk-fetch once per ticker per run (PRD 7.3), covering the full
    [start_date - lookback, end_date] window so every simulated day has
    enough trailing history. A fetch failure is logged and the ticker is
    dropped from the backtest (same "skip, don't crash" contract as the
    live engine's signal layer, architecture 7.2/PRD 7.3).
    """
    try:
        return get_daily_bars(
            db,
            ticker,
            LOOKBACK_CALENDAR_DAYS + (end_date - start_date).days,
            end_date,
            provider=provider,
        )
    except MarketDataFetchError as exc:
        logger.warning("backtest: market data fetch failed for %s: %s", ticker, exc)
        errors.append({"ticker": ticker, "error": str(exc)})
        return []


def _trading_days_held(entry_index: int, as_of_index: int) -> int:
    """Mirrors app/engine/runner.py's _trading_days_held, but counts bars
    directly from the in-memory per-ticker bar index (already known for
    the simulated day) instead of re-querying market_data_cache — same
    "bars strictly after entry through as_of inclusive" semantics so
    live and backtest max-hold counts agree (architecture 4.6).
    """
    return max(as_of_index - entry_index, 0)


def _process_exits(
    account: VirtualAccount,
    bar_date: datetime.date,
    indicator_sets: dict[str, IndicatorSet],
    bar_index_by_ticker: dict[str, int],
    backtest_run_id: int,
    db: Session,
) -> int:
    """Same ordering/contract as runner.py's _process_exits (exits first
    so cash/slots free up before entries), against the virtual account.
    """
    sells = 0
    for ticker in list(account.positions.keys()):
        indicator_set = indicator_sets.get(ticker)
        if indicator_set is None:
            continue  # no fresh data this simulated day; leave position untouched

        position = account.positions[ticker]
        days_held = _trading_days_held(position.entry_trading_days_index, bar_index_by_ticker[ticker])
        reason = check_exit(
            entry_price=float(position.entry_price),
            entry_date=position.entry_date,
            indicator_set=indicator_set,
            as_of_date=bar_date,
            trading_days_held=days_held,
        )
        if reason is None:
            continue

        price = decimal.Decimal(str(indicator_set.close))
        proceeds = price * position.quantity
        cost_basis = position.entry_price * position.quantity
        realized_pnl = proceeds - cost_basis

        db.add(
            BacktestTrade(
                backtest_run_id=backtest_run_id,
                ticker=ticker,
                side="SELL",
                quantity=position.quantity,
                price=price,
                trade_value=proceeds,
                bar_date=bar_date,
                signal_reason=reason,
                realized_pnl=realized_pnl,
            )
        )
        account.cash += proceeds
        account.realized_pnl += realized_pnl
        del account.positions[ticker]
        sells += 1

    return sells


def _process_entries(
    account: VirtualAccount,
    bar_date: datetime.date,
    signals: list,
    bar_index_by_ticker: dict[str, int],
    backtest_run_id: int,
    db: Session,
) -> int:
    """Same sizing contract as runner.py's _process_entries (10% of cash,
    max 5 concurrent, skip duplicate ticker / insufficient cash / slot
    cap), against the virtual account.
    """
    buys = 0
    for signal in signals:
        if len(account.positions) >= strategy_config.MAX_CONCURRENT_POSITIONS:
            break
        if signal.ticker in account.positions:
            continue

        price = decimal.Decimal(str(signal.price))
        if price <= 0:
            continue

        budget = account.cash * decimal.Decimal(str(strategy_config.POSITION_SIZE_PCT))
        quantity = int(budget // price)
        if quantity <= 0:
            continue

        cost = price * quantity
        if cost > account.cash:
            continue

        db.add(
            BacktestTrade(
                backtest_run_id=backtest_run_id,
                ticker=signal.ticker,
                side="BUY",
                quantity=quantity,
                price=price,
                trade_value=cost,
                bar_date=bar_date,
                signal_reason=signal.reason,
                realized_pnl=None,
            )
        )
        account.cash -= cost
        account.positions[signal.ticker] = VirtualPosition(
            ticker=signal.ticker,
            quantity=quantity,
            entry_price=price,
            entry_date=bar_date,
            entry_trading_days_index=bar_index_by_ticker[signal.ticker],
        )
        buys += 1

    return buys


def _mark_to_market(account: VirtualAccount, indicator_sets: dict[str, IndicatorSet]) -> decimal.Decimal:
    """Total portfolio value (cash + mark-to-market positions) at the
    close of a simulated day (PRD 6.4 equity curve). Positions with no
    fresh data this day keep their entry price as the last-known mark
    (same stale-mark fallback as the live engine, architecture 4.4).
    """
    equity = decimal.Decimal("0")
    for ticker, position in account.positions.items():
        indicator_set = indicator_sets.get(ticker)
        mark = decimal.Decimal(str(indicator_set.close)) if indicator_set is not None else position.entry_price
        equity += mark * position.quantity
    return account.cash + equity


def run_backtest(
    db: Session,
    backtest_run_id: int,
    start_date: datetime.date,
    end_date: datetime.date,
    tickers: list[str],
    starting_capital: decimal.Decimal,
    provider: MarketDataProvider | None = None,
) -> dict:
    """Day-by-day simulation over [start_date, end_date] (PRD 6.3), reusing
    the exact same signal/exit/sizing functions the live engine uses.
    Writes BacktestTrade rows scoped to `backtest_run_id` and returns a
    summary dict (equity_curve, total_return, win_rate, etc. — PRD 6.4)
    for the caller to store on the BacktestRun row.
    """
    errors: list[dict] = []
    bars_by_ticker: dict[str, list[Bar]] = {}
    for ticker in tickers:
        bars = _fetch_ticker_bars(db, ticker, start_date, end_date, errors, provider=provider)
        if bars:
            bars_by_ticker[ticker] = bars
    db.commit()  # persist any newly-cached market data independent of the backtest's own tables

    # Trading-day calendar for the simulation: the union of bar dates
    # within [start_date, end_date] across all tickers, since not every
    # ticker necessarily has a bar on every trading day (PRD: "daily-bar
    # simulation... bounded by how much historical daily data... the
    # free API tier provides").
    all_dates: set[datetime.date] = set()
    for bars in bars_by_ticker.values():
        all_dates.update(b.bar_date for b in bars if start_date <= b.bar_date <= end_date)
    trading_days = sorted(all_dates)

    account = VirtualAccount(cash=starting_capital)
    equity_curve: list[dict] = []

    for bar_date in trading_days:
        indicator_sets: dict[str, IndicatorSet] = {}
        bar_index_by_ticker: dict[str, int] = {}
        for ticker, bars in bars_by_ticker.items():
            # Bars up to and including this simulated day (oldest-first),
            # mirroring what the live engine's get_daily_bars(as_of=...)
            # would return for "today" — reuses compute_indicator_set
            # unchanged.
            window = [b for b in bars if b.bar_date <= bar_date]
            if not window or window[-1].bar_date != bar_date:
                continue  # no bar for this ticker on this trading day
            indicator_set = compute_indicator_set(window)
            if indicator_set is None:
                continue
            indicator_sets[ticker] = indicator_set
            bar_index_by_ticker[ticker] = len(window) - 1

        buy_signals = entry_signals(list(indicator_sets.values()))

        _process_exits(account, bar_date, indicator_sets, bar_index_by_ticker, backtest_run_id, db)
        _process_entries(account, bar_date, buy_signals, bar_index_by_ticker, backtest_run_id, db)

        total_value = _mark_to_market(account, indicator_sets)
        equity_curve.append({"date": bar_date.isoformat(), "total_value": str(total_value)})

    db.flush()
    summary = _compute_summary(db, backtest_run_id, starting_capital, equity_curve)
    summary["errors"] = errors
    return summary


def _compute_summary(
    db: Session,
    backtest_run_id: int,
    starting_capital: decimal.Decimal,
    equity_curve: list[dict],
) -> dict:
    """Summary metrics from PRD 6.4: total return, win rate, trade count,
    max drawdown, average holding period.
    """
    trades = (
        db.execute(
            select(BacktestTrade)
            .where(BacktestTrade.backtest_run_id == backtest_run_id)
            .order_by(BacktestTrade.bar_date, BacktestTrade.id)
        )
        .scalars()
        .all()
    )

    final_value = (
        decimal.Decimal(equity_curve[-1]["total_value"]) if equity_curve else starting_capital
    )
    total_return_abs = final_value - starting_capital
    total_return_pct = (
        (total_return_abs / starting_capital) * decimal.Decimal("100") if starting_capital > 0 else None
    )

    closed_trades = [t for t in trades if t.side == "SELL"]
    winning_trades = [t for t in closed_trades if (t.realized_pnl or decimal.Decimal("0")) > 0]
    win_rate = (
        decimal.Decimal(len(winning_trades)) / decimal.Decimal(len(closed_trades)) * decimal.Decimal("100")
        if closed_trades
        else None
    )

    avg_holding_days = None
    if closed_trades:
        buys_by_ticker_queue: dict[str, list] = {}
        holding_days: list[int] = []
        for t in trades:
            if t.side == "BUY":
                buys_by_ticker_queue.setdefault(t.ticker, []).append(t.bar_date)
            elif t.side == "SELL":
                queue = buys_by_ticker_queue.get(t.ticker)
                if queue:
                    entry_date = queue.pop(0)
                    holding_days.append((t.bar_date - entry_date).days)
        if holding_days:
            avg_holding_days = decimal.Decimal(sum(holding_days)) / decimal.Decimal(len(holding_days))

    max_drawdown_pct, max_drawdown_abs = _max_drawdown(equity_curve)

    return {
        "total_return_pct": total_return_pct,
        "total_return_abs": total_return_abs,
        "win_rate": win_rate,
        "total_trades": len(trades),
        "max_drawdown_pct": max_drawdown_pct,
        "max_drawdown_abs": max_drawdown_abs,
        "avg_holding_days": avg_holding_days,
        "equity_curve": equity_curve,
    }


def _max_drawdown(equity_curve: list[dict]) -> tuple[decimal.Decimal | None, decimal.Decimal | None]:
    """Largest peak-to-trough decline in the equity curve, in % and $
    (PRD 6.4). Returns (None, None) for an empty curve.
    """
    if not equity_curve:
        return None, None

    peak = decimal.Decimal(equity_curve[0]["total_value"])
    max_dd_abs = decimal.Decimal("0")
    max_dd_pct = decimal.Decimal("0")

    for point in equity_curve:
        value = decimal.Decimal(point["total_value"])
        if value > peak:
            peak = value
        drawdown_abs = peak - value
        drawdown_pct = (drawdown_abs / peak * decimal.Decimal("100")) if peak > 0 else decimal.Decimal("0")
        if drawdown_abs > max_dd_abs:
            max_dd_abs = drawdown_abs
        if drawdown_pct > max_dd_pct:
            max_dd_pct = drawdown_pct

    return max_dd_pct, max_dd_abs


def execute_backtest(
    backtest_run_id: int,
    start_date: datetime.date,
    end_date: datetime.date,
    tickers: list[str],
    starting_capital: decimal.Decimal,
    provider: MarketDataProvider | None = None,
    db: Session | None = None,
) -> None:
    """Background-thread entrypoint (PRD 6.5 queued -> running ->
    complete|failed). Opens its own session when run as a real
    BackgroundTask (mirrors app/scheduler.py's _run_scheduled_job, which
    also opens its own session since it runs off the request's thread);
    tests may pass `db` directly to run inline against the same sqlite
    session used to set up fixtures.
    """
    owns_session = db is None
    db = db or SessionLocal()
    try:
        run = db.get(BacktestRun, backtest_run_id)
        if run is None:
            logger.error("backtest run %s not found", backtest_run_id)
            return

        run.status = "running"
        db.commit()

        try:
            summary = run_backtest(
                db, backtest_run_id, start_date, end_date, tickers, starting_capital, provider=provider
            )
            run.status = "complete"
            run.total_return_pct = summary["total_return_pct"]
            run.total_return_abs = summary["total_return_abs"]
            run.win_rate = summary["win_rate"]
            run.total_trades = summary["total_trades"]
            run.max_drawdown_pct = summary["max_drawdown_pct"]
            run.max_drawdown_abs = summary["max_drawdown_abs"]
            run.avg_holding_days = summary["avg_holding_days"]
            run.equity_curve = summary["equity_curve"]
        except Exception:
            logger.exception("backtest run %s failed", backtest_run_id)
            db.rollback()
            run = db.get(BacktestRun, backtest_run_id)
            run.status = "failed"
        finally:
            run.finished_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
    finally:
        if owns_session:
            db.close()
