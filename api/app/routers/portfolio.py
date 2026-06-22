"""Self-service portfolio + trade-history router, plus the admin
trade-history endpoints that share the same row shape (architecture
Section 5.3, 5.4).

GET /me/account                       - account summary, zero-state safe
GET /me/positions                     - open positions + unrealized P&L
GET /me/trades                        - paginated, newest-first trade history
GET /admin/users/{id}/trades          - same shape, any user (admin only)
GET /admin/trades-today               - cross-user feed for today's run + summary

/me/* routes derive scope strictly from the token's user_id (require_auth
injects the current user) and never read a client-supplied user_id
(architecture 6.2, FR-11 AC3, FR-12 AC2).
"""

import csv
import datetime
import decimal
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db, require_admin, require_auth
from app.models import EngineRun, Position, Trade, User
from app.schemas.portfolio import (
    AccountSummary,
    PositionSummary,
    TradeListResponse,
    TradesTodayResponse,
    TradesTodaySummary,
    trade_to_summary,
)

router = APIRouter(tags=["portfolio"])

# DECIMAL(14,4) storage convention (architecture 3) -> always render money
# (and the unrealized_pnl_pct figure, kept at the same precision for
# simplicity) with 4 decimal places, matching what every Money column
# naturally produces, so zero-state/computed values aren't distinguishable
# from stored values by string shape alone.
ZERO = decimal.Decimal("0.0000")
_MONEY_QUANT = decimal.Decimal("0.0001")


def _money_str(value: decimal.Decimal) -> str:
    return str(value.quantize(_MONEY_QUANT))


@router.get("/me/account", response_model=AccountSummary)
def my_account(
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    account = user.account

    if account is None:
        # Defensive zero-state (shouldn't happen post-creation, every user
        # gets a 1:1 account — mirrors admin_users.py's _total_value
        # defensiveness). Still a valid payload, not an error (FR-9 AC2).
        zero = str(ZERO)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return AccountSummary(
            cash_balance=zero,
            equity_value=zero,
            total_value=zero,
            realized_pnl=zero,
            unrealized_pnl=zero,
            as_of=now,
        )

    positions = db.execute(select(Position).where(Position.user_id == user.id)).scalars().all()
    unrealized_pnl = ZERO
    for p in positions:
        mark = p.last_mark_price if p.last_mark_price is not None else p.entry_price
        unrealized_pnl += (mark - p.entry_price) * p.quantity

    total_value = account.cash_balance + account.equity_value

    return AccountSummary(
        cash_balance=str(account.cash_balance),
        equity_value=str(account.equity_value),
        total_value=str(total_value),
        realized_pnl=str(account.realized_pnl),
        unrealized_pnl=str(unrealized_pnl),
        as_of=account.updated_at.isoformat(),
    )


@router.get("/me/positions", response_model=list[PositionSummary])
def my_positions(
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    positions = db.execute(select(Position).where(Position.user_id == user.id)).scalars().all()
    today = datetime.date.today()

    items = []
    for p in positions:
        mark = p.last_mark_price if p.last_mark_price is not None else p.entry_price
        unrealized_abs = (mark - p.entry_price) * p.quantity
        # Assumption (noted per task instructions): days_held is calendar
        # days from entry_date to today, not trading days. The engine's
        # own max-hold check (app/engine/runner.py) counts trading days
        # internally; this display field is a simpler, user-facing
        # approximation, consistent with FR-10 AC1's plain "days held so
        # far" (no trading-calendar requirement stated there).
        days_held = (today - p.entry_date).days
        unrealized_pct = (
            (mark - p.entry_price) / p.entry_price * 100 if p.entry_price != ZERO else ZERO
        )

        items.append(
            PositionSummary(
                ticker=p.ticker,
                quantity=p.quantity,
                entry_price=_money_str(p.entry_price),
                entry_date=p.entry_date.isoformat(),
                days_held=days_held,
                current_price=_money_str(mark),
                unrealized_pnl_abs=_money_str(unrealized_abs),
                unrealized_pnl_pct=_money_str(unrealized_pct),
            )
        )

    return items


def _query_trades(
    db: Session,
    user_id: int,
    ticker: str | None,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
    page: int,
    page_size: int,
):
    """Shared paginated, newest-first trade query used by /me/trades and
    /admin/users/{id}/trades (architecture 5.4 "same shape, any user").
    """
    stmt = select(Trade).where(Trade.user_id == user_id)

    if ticker:
        stmt = stmt.where(Trade.ticker == ticker)
    if date_from:
        stmt = stmt.where(Trade.bar_date >= date_from)
    if date_to:
        stmt = stmt.where(Trade.bar_date <= date_to)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    page = max(page, 1)
    page_size = max(page_size, 1)
    stmt = (
        stmt.order_by(Trade.executed_at.desc(), Trade.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    trades = db.execute(stmt).scalars().all()

    return trades, total


@router.get("/me/trades", response_model=TradeListResponse)
def my_trades(
    ticker: str | None = None,
    from_: datetime.date | None = Query(None, alias="from"),
    to: datetime.date | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    # Scope is the token-derived `user.id` ONLY (FR-11 AC3 / architecture
    # 6.2) — there is deliberately no user_id query param accepted here,
    # so there is nothing for a malicious caller to override.
    trades, total = _query_trades(db, user.id, ticker, from_, to, page, page_size)
    return TradeListResponse(
        items=[trade_to_summary(t) for t in trades],
        total=total,
        page=max(page, 1),
        page_size=max(page_size, 1),
    )


@router.get("/admin/users/{user_id}/trades", response_model=TradeListResponse)
def user_trades(
    user_id: int,
    ticker: str | None = None,
    from_: datetime.date | None = Query(None, alias="from"),
    to: datetime.date | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    trades, total = _query_trades(db, user_id, ticker, from_, to, page, page_size)
    return TradeListResponse(
        items=[trade_to_summary(t) for t in trades],
        total=total,
        page=max(page, 1),
        page_size=max(page_size, 1),
    )


@router.get("/admin/trades-today")
def trades_today(
    ticker: str | None = None,
    side: str | None = None,
    user_id: int | None = None,
    format: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Cross-user feed for today's run + summary (architecture 5.4 /
    design 4.9). "Today" is interpreted as the bar_date of the most
    recent engine_runs row (not the wall-clock calendar date), since the
    engine's bar_date reflects the trading day actually evaluated, which
    may lag the calendar date over a weekend/holiday or before any run
    has happened today (assumption, noted since the architecture doesn't
    define "today" precisely for this admin view).
    """
    last_run = db.execute(select(EngineRun).order_by(EngineRun.started_at.desc())).scalars().first()

    stmt = select(Trade)
    if last_run is not None:
        stmt = stmt.where(Trade.engine_run_id == last_run.id)
    else:
        # No run has ever happened — nothing to show, not an error.
        stmt = stmt.where(Trade.id.is_(None))

    if ticker:
        stmt = stmt.where(Trade.ticker == ticker)
    if side:
        stmt = stmt.where(Trade.side == side)
    if user_id:
        stmt = stmt.where(Trade.user_id == user_id)

    stmt = stmt.order_by(Trade.executed_at.desc(), Trade.id.desc())
    trades = db.execute(stmt).scalars().all()

    users_evaluated = last_run.users_affected if last_run is not None else 0
    tickers_evaluated = last_run.tickers_evaluated if last_run is not None else 0
    signals_fired = last_run.signals_fired if last_run is not None else 0
    # "signals_skipped" isn't a stored engine_runs column (architecture
    # 3.2's engine_runs sketch has no such field); approximated here as
    # signals fired minus trades actually executed today, floored at 0
    # (a signal can be "skipped" per-user for slot/cash/dup reasons even
    # though it fired at the signal layer).
    signals_skipped = max(signals_fired - len(trades), 0)
    errors = last_run.errors if last_run is not None else []

    summary = TradesTodaySummary(
        trades=len(trades),
        users_evaluated=users_evaluated,
        signals_skipped=signals_skipped,
        errors=errors,
    )

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id", "user_id", "ticker", "side", "quantity", "price", "trade_value",
                "executed_at", "bar_date", "signal_reason", "realized_pnl", "position_id",
            ]
        )
        for t in trades:
            writer.writerow(
                [
                    t.id, t.user_id, t.ticker, t.side, t.quantity, t.price, t.trade_value,
                    t.executed_at.isoformat(), t.bar_date.isoformat(), t.signal_reason,
                    t.realized_pnl if t.realized_pnl is not None else "", t.position_id or "",
                ]
            )
        return Response(content=buffer.getvalue(), media_type="text/csv")

    return TradesTodayResponse(
        items=[trade_to_summary(t) for t in trades],
        summary=summary,
    )
