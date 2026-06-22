"""Admin user + fund management router (architecture Section 5.2).

Every route requires require_admin (403 for non-admin, FR-12 AC1).

GET    /admin/users              - paginated list, filter by status/q
POST   /admin/users              - create user + 1:1 account
GET    /admin/users/{id}         - full inspector payload
DELETE /admin/users/{id}         - soft-delete (is_active=false)
POST   /admin/users/{id}/fund    - top up cash_balance, write ledger row
"""

import decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db, require_admin
from app.models import Account, FundTransaction, Position, User
from app.schemas.admin import (
    AccountDetail,
    CreatedUserResponse,
    CreateUserRequest,
    FundRequest,
    FundResponse,
    PositionDetail,
    UserDetail,
    UserInspectorResponse,
    UserListResponse,
    UserSummary,
)
from app.security import hash_password

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def _total_value(account: Account | None) -> decimal.Decimal:
    """cash_balance + equity_value, or 0 if the user has no account yet
    (architecture 5.2 / PRD 3.4). Every user created via this router gets
    an account row, but this stays defensive in case data predates that.
    """
    if account is None:
        return decimal.Decimal("0")
    return account.cash_balance + account.equity_value


@router.get("", response_model=UserListResponse)
def list_users(
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    stmt = select(User)

    if status_filter == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status_filter == "deactivated":
        stmt = stmt.where(User.is_active.is_(False))

    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            (func.lower(User.display_name).like(like)) | (User.email_lower.like(like))
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    page = max(page, 1)
    page_size = max(page_size, 1)
    stmt = stmt.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    users = db.execute(stmt).scalars().all()

    items = [
        UserSummary(
            id=u.id,
            display_name=u.display_name,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            total_value=str(_total_value(u.account)),
        )
        for u in users
    ]
    return UserListResponse(items=items, total=total)


@router.post("", response_model=CreatedUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    email_lower = body.email.lower()
    existing = db.execute(
        select(User).where(User.email_lower == email_lower)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already in use")

    user = User(
        email=body.email,
        email_lower=email_lower,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    # 1:1 account, cash_balance defaults to 0 (architecture 3.1 / PRD 3.1).
    db.add(Account(user_id=user.id))
    db.commit()

    return CreatedUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.get("/{user_id}", response_model=UserInspectorResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    account = user.account
    account_detail = AccountDetail(
        cash_balance=str(account.cash_balance if account else decimal.Decimal("0")),
        equity_value=str(account.equity_value if account else decimal.Decimal("0")),
        realized_pnl=str(account.realized_pnl if account else decimal.Decimal("0")),
        total_value=str(_total_value(account)),
    )

    positions = db.execute(select(Position).where(Position.user_id == user_id)).scalars().all()
    position_details = [
        PositionDetail(
            ticker=p.ticker,
            quantity=p.quantity,
            entry_price=str(p.entry_price),
            entry_date=p.entry_date.isoformat(),
        )
        for p in positions
    ]

    return UserInspectorResponse(
        user=UserDetail(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            is_active=user.is_active,
        ),
        account=account_detail,
        positions=position_details,
    )


@router.delete("/{user_id}")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_active and user.role == "admin":
        # Last-admin guard (architecture 6.3 reference / PRD assumption 8,
        # 10.8): block deactivating the final active admin so the system
        # never ends up with zero usable admin logins.
        active_admin_count = db.execute(
            select(func.count()).where(User.role == "admin", User.is_active.is_(True))
        ).scalar_one()
        if active_admin_count <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="Cannot deactivate the last active admin"
            )

    user.is_active = False
    db.commit()

    return {"id": user.id, "is_active": user.is_active}


@router.post("/{user_id}/fund", response_model=FundResponse)
def fund_user(
    user_id: int,
    body: FundRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    account = user.account
    if account is None:
        # Defensive: every user created via POST /admin/users gets an
        # account, but guard against pre-existing data without one.
        account = Account(user_id=user.id)
        db.add(account)
        db.flush()

    # Decimal arithmetic throughout (architecture 3/5 conventions) — never
    # float. This is also literally the activation rule (architecture 4.2
    # / PRD 3.3): there is no separate "activate" toggle. The engine
    # selects accounts where cash_balance + equity_value > 0 on its next
    # run, so this funding call is what makes a $0 user eligible.
    account.cash_balance = account.cash_balance + body.amount

    db.add(
        FundTransaction(
            user_id=user.id,
            admin_id=admin.id,
            amount=body.amount,
            resulting_balance=account.cash_balance,
        )
    )
    db.commit()

    return FundResponse(new_balance=str(account.cash_balance))
