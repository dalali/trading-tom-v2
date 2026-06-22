"""Pydantic v2 request/response schemas for /admin/engine/* (architecture 5.5).

No money fields here (engine_runs has no monetary columns), so this
module diverges from app/schemas/portfolio.py's decimal-string
convention only because there is nothing to convert.
"""

import datetime

from pydantic import BaseModel


class EngineRunSummary(BaseModel):
    id: int
    trigger: str
    status: str
    started_at: str
    finished_at: str | None
    tickers_evaluated: int
    signals_fired: int
    trades_executed: int
    users_affected: int


class EngineRunDetail(EngineRunSummary):
    errors: list


class EngineStatusResponse(BaseModel):
    state: str
    last_run: EngineRunSummary | None
    next_scheduled_run: str | None
    progress: dict | None = None


class TriggerRunResponse(BaseModel):
    engine_run_id: int


class EngineRunListResponse(BaseModel):
    items: list[EngineRunSummary]
    total: int
    page: int
    page_size: int


def _iso(value: datetime.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def engine_run_to_summary(run) -> EngineRunSummary:
    return EngineRunSummary(
        id=run.id,
        trigger=run.trigger,
        status=run.status,
        started_at=_iso(run.started_at),
        finished_at=_iso(run.finished_at),
        tickers_evaluated=run.tickers_evaluated,
        signals_fired=run.signals_fired,
        trades_executed=run.trades_executed,
        users_affected=run.users_affected,
    )


def engine_run_to_detail(run) -> EngineRunDetail:
    return EngineRunDetail(
        **engine_run_to_summary(run).model_dump(),
        errors=run.errors or [],
    )
