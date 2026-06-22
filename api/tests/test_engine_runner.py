"""End-to-end tests for app/engine/runner.py: run_engine() against a
seeded sqlite DB with pre-populated market_data_cache rows (so no real
network/yfinance call ever happens — the cache-first read in
get_daily_bars finds everything it needs locally).
"""

import datetime
import decimal

import sqlalchemy as sa

from app.engine.runner import run_engine
from app.market_data import MarketDataFetchError, MarketDataProvider
from app.models import Account, EngineRun, MarketDataCache, Position, Trade, User
from app import strategy_config


class _AlwaysFailsProvider(MarketDataProvider):
    name = "fails"

    def _fetch(self, ticker, start, end):
        raise MarketDataFetchError(f"synthetic failure for {ticker}")


AS_OF = datetime.date(2024, 6, 3)  # arbitrary Monday


def _seed_cache(db, ticker, closes, start_date):
    d = start_date
    for c in closes:
        db.add(
            MarketDataCache(
                ticker=ticker,
                bar_date=d,
                open=decimal.Decimal(str(c)),
                high=decimal.Decimal(str(c)),
                low=decimal.Decimal(str(c)),
                close=decimal.Decimal(str(c)),
                volume=1_000_000,
                provider="fake",
            )
        )
        d += datetime.timedelta(days=1)
    db.commit()


def _trending_up_closes():
    """A gentle uptrend (SMA20 > SMA50) with a 4-day pullback (cools RSI
    below 70 and lets EMA10 dip to/below SMA20) followed by a pop on the
    final bar that pushes EMA10 back above SMA20 — engineered so all
    three entry conditions (architecture 4.3) hold simultaneously on the
    last bar. Verified numerically: trend filter holds, RSI ~= 67.5 (in
    [50,70]), and EMA10 crosses above SMA20 on the final bar.
    """
    closes = [100.0 + i * 0.2 for i in range(55)]
    for _ in range(4):
        closes.append(closes[-1] - 1.0)
    closes.append(closes[-1] + 5)
    return closes


def _make_user_and_account(db, email, cash):
    user = User(
        email=email,
        email_lower=email.lower(),
        display_name=email,
        password_hash="x",
        role="user",
        is_active=True,
    )
    db.add(user)
    db.flush()
    account = Account(user_id=user.id, cash_balance=decimal.Decimal(str(cash)))
    db.add(account)
    db.commit()
    return user, account


def test_run_engine_funded_account_enters_position_on_signal(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    user, account = _make_user_and_account(db, "trader@example.com", 100_000)

    ticker = strategy_config.UNIVERSE[0]
    closes = _trending_up_closes()
    start_date = AS_OF - datetime.timedelta(days=len(closes) - 1)
    _seed_cache(db, ticker, closes, start_date)

    engine_run = EngineRun(trigger="manual", status="running")
    db.add(engine_run)
    db.commit()

    summary = run_engine(db, engine_run.id, AS_OF, accounts=[account], universe=[ticker])

    db.refresh(account)
    positions = db.execute(
        sa.select(Position).where(Position.user_id == user.id)
    ).scalars().all()
    trades = db.execute(
        sa.select(Trade).where(Trade.user_id == user.id)
    ).scalars().all()

    assert summary["tickers_evaluated"] == 1
    assert summary["signals_fired"] == 1
    assert summary["trades_executed"] == 1
    assert summary["users_affected"] == 1
    assert len(positions) == 1
    assert positions[0].ticker == ticker
    expected_price = decimal.Decimal(str(closes[-1]))
    expected_qty = int((decimal.Decimal("100000") * decimal.Decimal("0.10")) // expected_price)
    assert positions[0].quantity == expected_qty
    assert len(trades) == 1
    assert trades[0].side == "BUY"
    assert trades[0].signal_reason == "ENTRY_TREND_MOMENTUM"
    assert account.cash_balance == decimal.Decimal("100000") - (expected_price * expected_qty)


def test_run_engine_skips_unfunded_account(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    user, account = _make_user_and_account(db, "broke@example.com", 0)

    ticker = strategy_config.UNIVERSE[0]
    closes = _trending_up_closes()
    start_date = AS_OF - datetime.timedelta(days=len(closes) - 1)
    _seed_cache(db, ticker, closes, start_date)

    engine_run = EngineRun(trigger="manual", status="running")
    db.add(engine_run)
    db.commit()

    from app.engine.runner import active_accounts

    eligible = active_accounts(db)
    assert account.user_id not in [a.user_id for a in eligible]

    summary = run_engine(db, engine_run.id, AS_OF, universe=[ticker])
    assert summary["users_affected"] == 0
    assert summary["trades_executed"] == 0


def test_run_engine_skips_deactivated_account(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    user, account = _make_user_and_account(db, "gone@example.com", 100_000)
    user.is_active = False
    db.commit()

    ticker = strategy_config.UNIVERSE[0]
    closes = _trending_up_closes()
    start_date = AS_OF - datetime.timedelta(days=len(closes) - 1)
    _seed_cache(db, ticker, closes, start_date)

    engine_run = EngineRun(trigger="manual", status="running")
    db.add(engine_run)
    db.commit()

    summary = run_engine(db, engine_run.id, AS_OF, universe=[ticker])
    assert summary["users_affected"] == 0
    assert summary["trades_executed"] == 0


def test_run_engine_exits_before_entries_and_updates_cash(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    user, account = _make_user_and_account(db, "holder@example.com", 50_000)

    ticker = strategy_config.UNIVERSE[1]
    # Build a flat-ish series so no entry signal fires, but seed an open
    # position that's already +9% (above the 8% profit target) so the
    # exit path is exercised independent of any new entry. Ends the day
    # before AS_OF so the AS_OF bar (seeded separately below) is free.
    closes = [100.0] * 60
    start_date = AS_OF - datetime.timedelta(days=len(closes))
    _seed_cache(db, ticker, closes, start_date)
    # AS_OF bar pops to +9% over a 100 entry price.
    db.add(
        MarketDataCache(
            ticker=ticker,
            bar_date=AS_OF,
            open=decimal.Decimal("109"),
            high=decimal.Decimal("109"),
            low=decimal.Decimal("109"),
            close=decimal.Decimal("109"),
            volume=1_000_000,
            provider="fake",
        )
    )
    db.commit()

    entry_trade = Trade(
        user_id=user.id,
        ticker=ticker,
        side="BUY",
        quantity=10,
        price=decimal.Decimal("100"),
        trade_value=decimal.Decimal("1000"),
        bar_date=start_date,
        signal_reason="ENTRY_TREND_MOMENTUM",
    )
    db.add(entry_trade)
    db.flush()
    position = Position(
        user_id=user.id,
        ticker=ticker,
        quantity=10,
        entry_price=decimal.Decimal("100"),
        entry_date=start_date,
        entry_trade_id=entry_trade.id,
        last_mark_price=decimal.Decimal("100"),
    )
    db.add(position)
    account.cash_balance = decimal.Decimal("49000")  # 50000 - 1000 cost basis
    db.commit()

    engine_run = EngineRun(trigger="manual", status="running")
    db.add(engine_run)
    db.commit()

    summary = run_engine(db, engine_run.id, AS_OF, accounts=[account], universe=[ticker])

    db.refresh(account)
    remaining_positions = db.execute(
        sa.select(Position).where(Position.user_id == user.id)
    ).scalars().all()
    sell_trades = db.execute(
        sa.select(Trade).where(Trade.user_id == user.id, Trade.side == "SELL")
    ).scalars().all()

    assert remaining_positions == []
    assert len(sell_trades) == 1
    assert sell_trades[0].signal_reason == "EXIT_PROFIT_TARGET"
    assert sell_trades[0].realized_pnl == decimal.Decimal("90")  # (109-100)*10
    assert account.cash_balance == decimal.Decimal("49000") + decimal.Decimal("1090")
    assert account.realized_pnl == decimal.Decimal("90")
    assert summary["trades_executed"] == 1


def test_run_engine_records_fetch_error_and_continues(db_session_with_engine_runs):
    db = db_session_with_engine_runs
    user, account = _make_user_and_account(db, "trader2@example.com", 100_000)

    # No market_data_cache rows for this ticker, and the provider is a
    # fake that always raises -> MarketDataFetchError, caught and
    # recorded, no real network call attempted.
    bad_ticker = "ZZZZ_NONEXISTENT_TICKER"

    engine_run = EngineRun(trigger="manual", status="running")
    db.add(engine_run)
    db.commit()

    summary = run_engine(
        db,
        engine_run.id,
        AS_OF,
        accounts=[account],
        universe=[bad_ticker],
        provider=_AlwaysFailsProvider(),
    )

    assert summary["tickers_evaluated"] == 1
    assert summary["trades_executed"] == 0
    assert len(summary["errors"]) == 1
    assert summary["errors"][0]["ticker"] == bad_ticker
