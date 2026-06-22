"""Admin engine-control router (architecture Section 5.5).

Every route requires require_admin (403 for non-admin, FR-12 AC1).

GET  /admin/engine/status     - {state, last_run, next_scheduled_run, progress?}
POST /admin/engine/run        - trigger a manual run -> 202; 409 if already running
GET  /admin/engine/runs       - paginated run history, newest first
GET  /admin/engine/runs/{id}  - full run detail incl. errors[]; 404 if not found
"""

import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import strategy_config
from app.deps import get_db, require_admin
from app.models import EngineRun, User
from app.scheduler import EngineRunInProgress, get_engine_status, trigger_manual_run
from app.schemas.engine import (
    EngineRunDetail,
    EngineRunListResponse,
    EngineStatusResponse,
    TriggerRunResponse,
    engine_run_to_detail,
    engine_run_to_summary,
)

router = APIRouter(prefix="/admin/engine", tags=["admin-engine"])


def _next_scheduled_run(now: datetime.datetime | None = None) -> str:
    """Next daily cron firing at strategy_config's configured hour/minute
    in its configured timezone (architecture 4.5/2.4 — APScheduler's own
    cron trigger is the source of truth for *actual* firing; this is a
    read-only projection for the status payload, not a second scheduler).
    """
    tz = ZoneInfo(strategy_config.ENGINE_SCHEDULE_TIMEZONE)
    now = now.astimezone(tz) if now is not None else datetime.datetime.now(tz)

    candidate = now.replace(
        hour=strategy_config.ENGINE_SCHEDULE_HOUR,
        minute=strategy_config.ENGINE_SCHEDULE_MINUTE,
        second=0,
        microsecond=0,
    )
    if candidate <= now:
        candidate += datetime.timedelta(days=1)
    return candidate.isoformat()


@router.get("/status", response_model=EngineStatusResponse)
def status_endpoint(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    engine_status = get_engine_status(db)
    last_run = engine_status["last_run"]
    return EngineStatusResponse(
        state=engine_status["state"],
        last_run=engine_run_to_summary(last_run) if last_run is not None else None,
        next_scheduled_run=_next_scheduled_run(),
        progress=None,
    )


@router.post("/run", response_model=TriggerRunResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_run(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    try:
        run = trigger_manual_run(db)
    except EngineRunInProgress as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return TriggerRunResponse(engine_run_id=run.id)


@router.get("/runs", response_model=EngineRunListResponse)
def list_runs(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    page = max(page, 1)
    page_size = max(page_size, 1)

    total = db.execute(select(func.count()).select_from(EngineRun)).scalar_one()

    runs = (
        db.execute(
            select(EngineRun)
            .order_by(EngineRun.started_at.desc(), EngineRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return EngineRunListResponse(
        items=[engine_run_to_summary(r) for r in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/runs/{run_id}", response_model=EngineRunDetail)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    run = db.get(EngineRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Engine run not found")

    return engine_run_to_detail(run)
