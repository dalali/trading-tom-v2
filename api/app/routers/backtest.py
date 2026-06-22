"""Admin backtest router (architecture Section 5.6, 5.7).

Every route requires require_admin (403 for non-admin, FR-12 AC1).

POST /admin/backtests              - queue a backtest run -> 202; 400 on bad range
GET  /admin/backtests               - paginated list with headline metrics
GET  /admin/backtests/{id}          - full result incl. equity_curve + trades
GET  /admin/market-data/range       - {earliest, latest} cached provider range
GET  /admin/market-data/universe    - configured watchlist tickers
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import strategy_config
from app.deps import get_db, require_admin
from app.engine.backtest import BacktestValidationError, execute_backtest, get_market_data_range, validate_date_range
from app.models import BacktestRun, BacktestTrade, User
from app.schemas.backtest import (
    BacktestRunDetail,
    BacktestRunListResponse,
    CreateBacktestRequest,
    CreateBacktestResponse,
    MarketDataRangeResponse,
    backtest_run_to_detail,
    backtest_run_to_summary,
)

router = APIRouter(tags=["admin-backtest"])


@router.post("/admin/backtests", response_model=CreateBacktestResponse, status_code=status.HTTP_202_ACCEPTED)
def create_backtest(
    request: CreateBacktestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    tickers = request.resolved_tickers()

    try:
        validate_date_range(db, request.start_date, request.end_date, tickers)
    except BacktestValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    run = BacktestRun(
        created_by=admin.id,
        start_date=request.start_date,
        end_date=request.end_date,
        tickers=tickers,
        starting_capital=request.starting_capital,
        status="queued",
    )
    db.add(run)
    db.commit()

    background_tasks.add_task(
        execute_backtest,
        run.id,
        request.start_date,
        request.end_date,
        tickers,
        request.starting_capital,
    )

    return CreateBacktestResponse(backtest_run_id=run.id, status="queued")


@router.get("/admin/backtests", response_model=BacktestRunListResponse)
def list_backtests(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    page = max(page, 1)
    page_size = max(page_size, 1)

    total = db.execute(select(func.count()).select_from(BacktestRun)).scalar_one()

    runs = (
        db.execute(
            select(BacktestRun)
            .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return BacktestRunListResponse(
        items=[backtest_run_to_summary(r) for r in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/admin/backtests/{run_id}", response_model=BacktestRunDetail)
def get_backtest(
    run_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Backtest run not found")

    trades = (
        db.execute(
            select(BacktestTrade)
            .where(BacktestTrade.backtest_run_id == run_id)
            .order_by(BacktestTrade.bar_date, BacktestTrade.id)
        )
        .scalars()
        .all()
    )

    return backtest_run_to_detail(run, trades)


@router.get("/admin/market-data/range", response_model=MarketDataRangeResponse)
def market_data_range(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    earliest, latest = get_market_data_range(db)
    return MarketDataRangeResponse(
        earliest=earliest.isoformat() if earliest else None,
        latest=latest.isoformat() if latest else None,
    )


@router.get("/admin/market-data/universe")
def market_data_universe(
    _admin: User = Depends(require_admin),
):
    return list(strategy_config.UNIVERSE)
