"""Model-layer tests: import safety + expected schema shape.

These intentionally do not require a live Postgres. They verify (a)
all models import without touching the DB, (b) all 9 architecture 3.2
tables are registered on Base.metadata, and (c) the DDL compiles
cleanly against the postgresql dialect (the only supported deployment
target — see architecture 8.1), catching typos in column/constraint
definitions without needing a live connection.
"""

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app import models
from app.db import Base

EXPECTED_TABLES = {
    "users",
    "accounts",
    "fund_transactions",
    "positions",
    "trades",
    "engine_runs",
    "backtest_runs",
    "backtest_trades",
    "market_data_cache",
}


def test_all_expected_tables_registered():
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def test_ddl_compiles_for_every_table_against_postgres_dialect():
    for table in Base.metadata.sorted_tables:
        # Raises if a column/constraint definition is invalid; this is
        # the same compilation path `alembic upgrade head` exercises.
        sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "CREATE TABLE" in sql


def test_users_email_lower_is_unique():
    users = Base.metadata.tables["users"]
    unique_cols = {tuple(c.columns.keys()) for c in users.constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert ("email_lower",) in unique_cols


def test_positions_user_ticker_is_unique():
    positions = Base.metadata.tables["positions"]
    unique_cols = {
        tuple(c.columns.keys()) for c in positions.constraints if c.__class__.__name__ == "UniqueConstraint"
    }
    assert ("user_id", "ticker") in unique_cols


def test_market_data_cache_ticker_bar_date_is_unique():
    cache = Base.metadata.tables["market_data_cache"]
    unique_cols = {tuple(c.columns.keys()) for c in cache.constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert ("ticker", "bar_date") in unique_cols


def test_money_columns_are_fixed_point_decimal():
    # Spot-check a few money columns are NUMERIC(14, 4), never float.
    accounts = Base.metadata.tables["accounts"]
    cash_balance = accounts.columns["cash_balance"]
    assert cash_balance.type.precision == 14
    assert cash_balance.type.scale == 4

    trades = Base.metadata.tables["trades"]
    price = trades.columns["price"]
    assert price.type.precision == 14
    assert price.type.scale == 4
