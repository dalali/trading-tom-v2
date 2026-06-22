"""Pydantic v2 request/response schemas for /admin/backtests* and
/admin/market-data/range (architecture 5.6, 5.7; PRD Section 6).

Money fields are decimal strings over the wire (architecture 5/
assumption 5), matching app/schemas/portfolio.py's convention, even
though backtests never touch real accounts — the same DECIMAL(14,4)
float-drift concern applies to starting_capital/return figures.
"""

import datetime
import decimal

from pydantic import BaseModel, field_validator

from app import strategy_config

DEFAULT_STARTING_CAPITAL = decimal.Decimal("100000")


class CreateBacktestRequest(BaseModel):
    start_date: datetime.date
    end_date: datetime.date
    tickers: list[str] | None = None
    starting_capital: decimal.Decimal = DEFAULT_STARTING_CAPITAL

    @field_validator("starting_capital")
    @classmethod
    def _validate_starting_capital(cls, v: decimal.Decimal) -> decimal.Decimal:
        if v <= 0:
            raise ValueError("starting_capital must be > 0")
        return v

    @field_validator("tickers")
    @classmethod
    def _validate_tickers(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) == 0:
            raise ValueError("tickers must be a non-empty list if provided")
        return v

    def resolved_tickers(self) -> list[str]:
        """Defaults to the full live-engine universe (PRD 6.2) when the
        admin doesn't narrow it to a subset.
        """
        return self.tickers if self.tickers is not None else list(strategy_config.UNIVERSE)


class CreateBacktestResponse(BaseModel):
    backtest_run_id: int
    status: str


class BacktestRunSummary(BaseModel):
    id: int
    created_by: int
    start_date: str
    end_date: str
    tickers: list[str]
    starting_capital: str
    status: str
    total_return_pct: str | None
    total_return_abs: str | None
    win_rate: str | None
    total_trades: int | None
    max_drawdown_pct: str | None
    max_drawdown_abs: str | None
    avg_holding_days: str | None
    created_at: str
    finished_at: str | None


class BacktestTradeSummary(BaseModel):
    id: int
    ticker: str
    side: str
    quantity: int
    price: str
    trade_value: str
    bar_date: str
    signal_reason: str
    realized_pnl: str | None


class EquityCurvePoint(BaseModel):
    date: str
    total_value: str


class BacktestRunDetail(BacktestRunSummary):
    equity_curve: list[EquityCurvePoint]
    backtest_trades: list[BacktestTradeSummary]


class BacktestRunListResponse(BaseModel):
    items: list[BacktestRunSummary]
    total: int
    page: int
    page_size: int


class MarketDataRangeResponse(BaseModel):
    earliest: str | None
    latest: str | None


def _str(value: decimal.Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _date_str(value: datetime.date | None) -> str | None:
    return value.isoformat() if value is not None else None


def backtest_run_to_summary(run) -> BacktestRunSummary:
    return BacktestRunSummary(
        id=run.id,
        created_by=run.created_by,
        start_date=_date_str(run.start_date),
        end_date=_date_str(run.end_date),
        tickers=run.tickers,
        starting_capital=str(run.starting_capital),
        status=run.status,
        total_return_pct=_str(run.total_return_pct),
        total_return_abs=_str(run.total_return_abs),
        win_rate=_str(run.win_rate),
        total_trades=run.total_trades,
        max_drawdown_pct=_str(run.max_drawdown_pct),
        max_drawdown_abs=_str(run.max_drawdown_abs),
        avg_holding_days=_str(run.avg_holding_days),
        created_at=run.created_at.isoformat() if run.created_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
    )


def backtest_trade_to_summary(trade) -> BacktestTradeSummary:
    return BacktestTradeSummary(
        id=trade.id,
        ticker=trade.ticker,
        side=trade.side,
        quantity=trade.quantity,
        price=str(trade.price),
        trade_value=str(trade.trade_value),
        bar_date=_date_str(trade.bar_date),
        signal_reason=trade.signal_reason,
        realized_pnl=_str(trade.realized_pnl),
    )


def backtest_run_to_detail(run, trades: list) -> BacktestRunDetail:
    equity_curve = [
        EquityCurvePoint(date=point["date"], total_value=str(point["total_value"]))
        for point in (run.equity_curve or [])
    ]
    return BacktestRunDetail(
        **backtest_run_to_summary(run).model_dump(),
        equity_curve=equity_curve,
        backtest_trades=[backtest_trade_to_summary(t) for t in trades],
    )
