"""FastAPI application entrypoint.

Import-safe: no DB connection happens at import time. Migrations and
admin bootstrap run in start.sh before uvicorn starts this app, per
architecture Section 8.1.
"""

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import admin_users, auth, backtest, engine, portfolio


def _scheduler_should_start() -> bool:
    """Guard against starting APScheduler during tests or plain import
    (architecture 2.4 "single Uvicorn process" caveat — a second
    scheduler instance, e.g. one started incidentally by importing
    app.main in a test process, must never fire the cron job). Checks
    for pytest in sys.modules (set whenever the test suite imports this
    module, including via TestClient) in addition to the explicit
    settings.enable_scheduler override.
    """
    if "pytest" in sys.modules:
        return False
    return settings.enable_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No startup DB work here by design (architecture 8.1 / assumption 8):
    # migrations + admin bootstrap run in start.sh, before this process
    # starts, not at app import/startup time. The scheduler is the one
    # exception — it has no DB-at-import-time cost (APScheduler just
    # registers a cron job; the job itself opens its own session only
    # when it fires) and architecture 2.4/4.5 requires it be running for
    # the daily 17:00 ET trade cycle to actually happen.
    scheduler = None
    if _scheduler_should_start():
        from app.scheduler import start_scheduler

        scheduler = start_scheduler()

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)
app.include_router(auth.router)
app.include_router(admin_users.router)
app.include_router(engine.router)
app.include_router(portfolio.router)
app.include_router(backtest.router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Architecture 5 conventions say bad input (weak password, malformed
    # email, fund amount <= 0) is a 400, not FastAPI/Pydantic's default
    # 422. Reusing the same {"detail": ...} error shape as the rest of
    # the API (architecture 5 conventions intro).
    errors = exc.errors()
    message = errors[0]["msg"] if errors else "Invalid request"
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": message})


@app.get("/health")
def health():
    return {"status": "ok"}
