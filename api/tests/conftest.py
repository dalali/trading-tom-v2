"""Shared test fixtures.

Tests run against an in-memory sqlite DB, never a live Postgres
(per task requirements). Two of the ORM tables (engine_runs,
backtest_runs) use Postgres-only JSONB columns and a few others use
BigInteger autoincrement PKs, which sqlite's autoincrement rowid
machinery only recognizes on Integer-typed PKs — both are harmless
Postgres-vs-sqlite divergences, not bugs in the schema (verified
separately in test_models.py by compiling DDL against the postgresql
dialect). The `sqlite_engine`/`db_session` fixtures below build a
sqlite-compatible subset of the schema sufficient for exercising
business logic (bootstrap) without a live DB.
"""

import os

# Settings are read at import time; provide harmless defaults so
# importing app.config / app.db never requires a real DATABASE_URL.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Integer, create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models
from app.db import Base

# Tables that are sqlite-safe as-is (no JSONB columns).
SQLITE_SAFE_TABLES = [
    models.User.__table__,
    models.Account.__table__,
    models.FundTransaction.__table__,
    models.Position.__table__,
    models.Trade.__table__,
    models.BacktestTrade.__table__,
    models.MarketDataCache.__table__,
]

# engine_runs uses a Postgres JSONB column (`errors`); sqlite has no JSONB
# type, but SQLAlchemy's generic JSON type compiles to sqlite's native
# JSON1-backed TEXT storage, which is sufficient for the engine-runner
# tests (which only need to read/write a list of dicts, not query inside
# it). Coerced only for the sqlite test engine via the same before_create
# event-listener pattern used for the BigInteger->Integer PK shim below;
# the real Postgres schema (and its JSONB type) is untouched.
ENGINE_RUNS_TABLE = models.EngineRun.__table__

# backtest_runs uses two Postgres JSONB columns (`tickers`, `equity_curve`);
# same sqlite-JSON-shim approach as engine_runs above.
BACKTEST_RUNS_TABLE = models.BacktestRun.__table__


def _coerce_jsonb_to_json(target, connection, **kw):
    target.columns["errors"].type = JSON()


def _coerce_backtest_jsonb_to_json(target, connection, **kw):
    target.columns["tickers"].type = JSON()
    target.columns["equity_curve"].type = JSON()


event.listens_for(ENGINE_RUNS_TABLE, "before_create")(_coerce_jsonb_to_json)
event.listens_for(BACKTEST_RUNS_TABLE, "before_create")(_coerce_backtest_jsonb_to_json)

# BigInteger autoincrement PKs need to be Integer for sqlite's rowid
# autoincrement to apply; Postgres uses BIGSERIAL regardless of this
# sqlite-only shim (see test_models.py for the Postgres DDL check).
_PK_TABLES = [*SQLITE_SAFE_TABLES, ENGINE_RUNS_TABLE, BACKTEST_RUNS_TABLE]


def _coerce_bigint_pk_to_integer(target, connection, **kw):
    target.columns["id"].type = Integer()


for _table in _PK_TABLES:
    event.listens_for(_table, "before_create")(_coerce_bigint_pk_to_integer)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=SQLITE_SAFE_TABLES)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def db_session_with_engine_runs():
    """Like db_session, but also includes the engine_runs table (sqlite-
    compatible JSON shim above) for tests exercising app/engine/runner.py
    and app/scheduler.py end-to-end.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[*SQLITE_SAFE_TABLES, ENGINE_RUNS_TABLE])
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def db_session_with_backtest_runs():
    """Like db_session, but also includes the backtest_runs table (sqlite-
    compatible JSON shim above) for tests exercising app/engine/backtest.py
    end-to-end without going through the TestClient.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[*SQLITE_SAFE_TABLES, BACKTEST_RUNS_TABLE])
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def db_session_for_client():
    """Like db_session, but uses StaticPool + check_same_thread=False so
    the single in-memory sqlite connection can be shared between the
    test's thread and TestClient's request-handling thread (FastAPI's
    TestClient dispatches requests on a worker thread).
    """
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=SQLITE_SAFE_TABLES)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session_for_client):
    """TestClient with the get_db dependency overridden to the same
    sqlite session used directly by tests, so a test can set up rows
    via db_session and then hit the API and see them.
    """
    from app.deps import get_db
    from app.main import app

    def _override_get_db():
        yield db_session_for_client

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def db_session_for_client_with_engine_runs():
    """Like db_session_for_client, but also includes the engine_runs
    table (sqlite-compatible JSON shim, see ENGINE_RUNS_TABLE above) so
    HTTP-level tests for /admin/engine/* and /me/trades-adjacent routes
    that join against engine_runs can run through the real TestClient.
    """
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[*SQLITE_SAFE_TABLES, ENGINE_RUNS_TABLE])
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client_with_engine_runs(db_session_for_client_with_engine_runs):
    """Like `client`, but backed by db_session_for_client_with_engine_runs
    so routes that read/write engine_runs (the engine router, and
    /admin/trades-today which joins trades to the latest run) work
    end-to-end over HTTP in tests.
    """
    from app.deps import get_db
    from app.main import app

    def _override_get_db():
        yield db_session_for_client_with_engine_runs

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def db_session_for_client_with_backtest_runs():
    """Like db_session_for_client, but also includes the backtest_runs
    table (sqlite-compatible JSON shim, see BACKTEST_RUNS_TABLE above) so
    HTTP-level tests for /admin/backtests* can run through the real
    TestClient.
    """
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[*SQLITE_SAFE_TABLES, BACKTEST_RUNS_TABLE])
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client_with_backtest_runs(db_session_for_client_with_backtest_runs):
    """Like `client`, but backed by db_session_for_client_with_backtest_runs
    so /admin/backtests* routes (which read/write backtest_runs) work
    end-to-end over HTTP in tests.
    """
    from app.deps import get_db
    from app.main import app

    def _override_get_db():
        yield db_session_for_client_with_backtest_runs

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
