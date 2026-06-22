"""Pydantic v2 request/response schemas for /me/* and admin trade-history
routes (architecture 5.3, 5.4).

Money fields are decimal strings over the wire (architecture 5/assumption
5), not floats, to avoid JSON float drift versus the DECIMAL(14,4)
storage. Like app/schemas/admin.py, this stays consistent with the rest
of the codebase rather than using pydantic's EmailStr/etc. (not relevant
here, no email fields).
"""

import datetime

from pydantic import BaseModel


class AccountSummary(BaseModel):
    cash_balance: str
    equity_value: str
    total_value: str
    realized_pnl: str
    unrealized_pnl: str
    as_of: str


class PositionSummary(BaseModel):
    ticker: str
    quantity: int
    entry_price: str
    entry_date: str
    days_held: int
    current_price: str
    unrealized_pnl_abs: str
    unrealized_pnl_pct: str


class TradeSummary(BaseModel):
    id: int
    ticker: str
    side: str
    quantity: int
    price: str
    trade_value: str
    executed_at: str
    bar_date: str
    signal_reason: str
    # NULL on BUY (architecture 5.4 / PRD 5.2) -> None over the wire.
    realized_pnl: str | None
    position_id: int | None


class TradeListResponse(BaseModel):
    items: list[TradeSummary]
    total: int
    page: int
    page_size: int


class TradesTodaySummary(BaseModel):
    trades: int
    users_evaluated: int
    signals_skipped: int
    errors: list


class TradesTodayResponse(BaseModel):
    items: list[TradeSummary]
    summary: TradesTodaySummary


def trade_to_summary(trade) -> TradeSummary:
    """Shared trade-row -> wire-shape mapping used by /me/trades,
    /admin/users/{id}/trades, and /admin/trades-today (architecture 5.4 —
    all three routes return "same shape" rows).
    """
    return TradeSummary(
        id=trade.id,
        ticker=trade.ticker,
        side=trade.side,
        quantity=trade.quantity,
        price=str(trade.price),
        trade_value=str(trade.trade_value),
        executed_at=trade.executed_at.isoformat() if isinstance(trade.executed_at, datetime.datetime) else str(trade.executed_at),
        bar_date=trade.bar_date.isoformat() if isinstance(trade.bar_date, datetime.date) else str(trade.bar_date),
        signal_reason=trade.signal_reason,
        realized_pnl=str(trade.realized_pnl) if trade.realized_pnl is not None else None,
        position_id=trade.position_id,
    )
