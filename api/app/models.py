"""SQLAlchemy 2.x ORM models for all tables in architecture Section 3.2.

Conventions used throughout (architecture Section 3):
- Money columns: DECIMAL(14,4), never float.
- Timestamps: TIMESTAMPTZ, stored UTC. Trading "bar dates" are a plain
  DATE column where the PRD calls out a distinct trading-day concept.
- Primary keys: BIGINT identity (architecture assumption 3 says either
  BIGINT identity or UUID is acceptable; BIGINT identity chosen).
- `role`, `side`, `signal_reason`, etc. are modeled as plain TEXT with a
  CHECK constraint rather than native Postgres ENUM types, so adding a
  new value later is a constraint change, not a type migration.
"""

import datetime
import decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(14, 4)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Case-insensitive unique email (architecture 3.2). Using a
        # functional unique index on lower(email) avoids depending on
        # the citext extension being installed.
        UniqueConstraint("email_lower", name="uq_users_email_lower"),
        CheckConstraint("role IN ('admin', 'user')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    # Stores email.lower() so the unique constraint above is effectively
    # case-insensitive (PRD 3.1 "email must be unique").
    email_lower: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    account: Mapped["Account"] = relationship(back_populates="user", uselist=False)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, unique=True
    )
    cash_balance: Mapped[decimal.Decimal] = mapped_column(
        Money, nullable=False, default=decimal.Decimal("0")
    )
    equity_value: Mapped[decimal.Decimal] = mapped_column(
        Money, nullable=False, default=decimal.Decimal("0")
    )
    realized_pnl: Mapped[decimal.Decimal] = mapped_column(
        Money, nullable=False, default=decimal.Decimal("0")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="account")


class FundTransaction(Base):
    __tablename__ = "fund_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    resulting_balance: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_positions_user_ticker"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    entry_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    entry_trade_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("trades.id"), nullable=False)
    last_mark_price: Mapped[decimal.Decimal | None] = mapped_column(Money, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_trades_side"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    trade_value: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    executed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    bar_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    signal_reason: Mapped[str] = mapped_column(Text, nullable=False)
    realized_pnl: Mapped[decimal.Decimal | None] = mapped_column(Money, nullable=True)
    # Intentionally not an FK to positions.id: positions rows are deleted
    # when a position closes (architecture 3.2), but this SELL trade row
    # must persist forever as part of the immutable trade log, so it
    # cannot reference a row that may no longer exist.
    position_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    engine_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("engine_runs.id"), nullable=True
    )


class EngineRun(Base):
    __tablename__ = "engine_runs"
    __table_args__ = (
        CheckConstraint("trigger IN ('scheduled', 'manual')", name="ck_engine_runs_trigger"),
        CheckConstraint(
            "status IN ('running', 'complete', 'failed')", name="ck_engine_runs_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tickers_evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_fired: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trades_executed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    users_affected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'complete', 'failed')",
            name="ck_backtest_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    tickers: Mapped[list] = mapped_column(JSONB, nullable=False)
    starting_capital: Mapped[decimal.Decimal] = mapped_column(
        Money, nullable=False, default=decimal.Decimal("100000")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    total_return_pct: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    total_return_abs: Mapped[decimal.Decimal | None] = mapped_column(Money, nullable=True)
    win_rate: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    total_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_drawdown_pct: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    max_drawdown_abs: Mapped[decimal.Decimal | None] = mapped_column(Money, nullable=True)
    avg_holding_days: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    equity_curve: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_backtest_trades_side"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backtest_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("backtest_runs.id"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    trade_value: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    bar_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    signal_reason: Mapped[str] = mapped_column(Text, nullable=False)
    realized_pnl: Mapped[decimal.Decimal | None] = mapped_column(Money, nullable=True)


class MarketDataCache(Base):
    __tablename__ = "market_data_cache"
    __table_args__ = (
        UniqueConstraint("ticker", "bar_date", name="uq_market_data_cache_ticker_bar_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    bar_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    open: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    high: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    low: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    close: Mapped[decimal.Decimal] = mapped_column(Money, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
