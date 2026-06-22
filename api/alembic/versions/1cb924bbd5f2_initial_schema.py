"""initial schema

Revision ID: 1cb924bbd5f2
Revises:
Create Date: 2026-06-22 00:00:00.000000

Creates all tables from architecture Section 3.2: users, accounts,
fund_transactions, positions, trades, engine_runs, backtest_runs,
backtest_trades, market_data_cache.

Hand-written (no live Postgres available in this environment to run
`alembic revision --autogenerate`); DDL was verified against the ORM
models in app/models.py by compiling CreateTable() for every table
against the postgresql dialect and reviewing the output.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1cb924bbd5f2"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_lower", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_lower", name="uq_users_email_lower"),
        sa.CheckConstraint("role IN ('admin', 'user')", name="ck_users_role"),
    )

    op.create_table(
        "engine_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tickers_evaluated", sa.Integer(), nullable=False),
        sa.Column("signals_fired", sa.Integer(), nullable=False),
        sa.Column("trades_executed", sa.Integer(), nullable=False),
        sa.Column("users_affected", sa.Integer(), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("trigger IN ('scheduled', 'manual')", name="ck_engine_runs_trigger"),
        sa.CheckConstraint("status IN ('running', 'complete', 'failed')", name="ck_engine_runs_status"),
    )

    op.create_table(
        "market_data_cache",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("bar_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(14, 4), nullable=False),
        sa.Column("high", sa.Numeric(14, 4), nullable=False),
        sa.Column("low", sa.Numeric(14, 4), nullable=False),
        sa.Column("close", sa.Numeric(14, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "bar_date", name="uq_market_data_cache_ticker_bar_date"),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("cash_balance", sa.Numeric(14, 4), nullable=False),
        sa.Column("equity_value", sa.Numeric(14, 4), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(14, 4), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "fund_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("resulting_balance", sa.Numeric(14, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("tickers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("starting_capital", sa.Numeric(14, 4), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_return_pct", sa.Numeric(14, 4), nullable=True),
        sa.Column("total_return_abs", sa.Numeric(14, 4), nullable=True),
        sa.Column("win_rate", sa.Numeric(14, 4), nullable=True),
        sa.Column("total_trades", sa.Integer(), nullable=True),
        sa.Column("max_drawdown_pct", sa.Numeric(14, 4), nullable=True),
        sa.Column("max_drawdown_abs", sa.Numeric(14, 4), nullable=True),
        sa.Column("avg_holding_days", sa.Numeric(14, 4), nullable=True),
        sa.Column("equity_curve", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('queued', 'running', 'complete', 'failed')", name="ck_backtest_runs_status"),
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(14, 4), nullable=False),
        sa.Column("trade_value", sa.Numeric(14, 4), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("bar_date", sa.Date(), nullable=False),
        sa.Column("signal_reason", sa.Text(), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(14, 4), nullable=True),
        sa.Column("position_id", sa.BigInteger(), nullable=True),
        sa.Column("engine_run_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["engine_run_id"], ["engine_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_trades_side"),
    )
    op.create_index("ix_trades_user_id_executed_at", "trades", ["user_id", "executed_at"], unique=False)
    op.create_index("ix_trades_user_id_ticker", "trades", ["user_id", "ticker"], unique=False)
    op.create_index("ix_trades_engine_run_id", "trades", ["engine_run_id"], unique=False)

    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("backtest_run_id", sa.BigInteger(), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(14, 4), nullable=False),
        sa.Column("trade_value", sa.Numeric(14, 4), nullable=False),
        sa.Column("bar_date", sa.Date(), nullable=False),
        sa.Column("signal_reason", sa.Text(), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(14, 4), nullable=True),
        sa.ForeignKeyConstraint(["backtest_run_id"], ["backtest_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_backtest_trades_side"),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("entry_price", sa.Numeric(14, 4), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_trade_id", sa.BigInteger(), nullable=False),
        sa.Column("last_mark_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["entry_trade_id"], ["trades.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "ticker", name="uq_positions_user_ticker"),
    )


def downgrade() -> None:
    op.drop_table("positions")
    op.drop_table("backtest_trades")
    op.drop_index("ix_trades_engine_run_id", table_name="trades")
    op.drop_index("ix_trades_user_id_ticker", table_name="trades")
    op.drop_index("ix_trades_user_id_executed_at", table_name="trades")
    op.drop_table("trades")
    op.drop_table("backtest_runs")
    op.drop_table("fund_transactions")
    op.drop_table("accounts")
    op.drop_table("market_data_cache")
    op.drop_table("engine_runs")
    op.drop_table("users")
