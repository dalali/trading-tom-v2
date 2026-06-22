"""Pydantic v2 request/response schemas for /admin/users* (architecture 5.2).

Money fields are decimal strings over the wire (architecture 5/assumption
5), not floats, to avoid JSON float drift versus the DECIMAL(14,4) storage.

Assumption: like app/schemas/auth.py, email is validated as a plain `str`
with a minimal regex check here (not pydantic's `EmailStr`, which needs
the optional `email-validator` package not in requirements.txt). Unlike
login, user *creation* is a write/admin action, not a login attempt, so
a 400 on a malformed email is appropriate here (no account-enumeration
concern — this isn't a public endpoint).
"""

import re
import decimal

from pydantic import BaseModel, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8


class CreateUserRequest(BaseModel):
    email: str
    display_name: str
    password: str
    role: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        return v

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: str) -> str:
        if v not in ("admin", "user"):
            raise ValueError("role must be 'admin' or 'user'")
        return v


class UserSummary(BaseModel):
    id: int
    display_name: str
    email: str
    role: str
    is_active: bool
    # Decimal string over the wire (architecture 5 conventions).
    total_value: str


class UserListResponse(BaseModel):
    items: list[UserSummary]
    total: int


class CreatedUserResponse(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    is_active: bool


class AccountDetail(BaseModel):
    cash_balance: str
    equity_value: str
    realized_pnl: str
    total_value: str


class PositionDetail(BaseModel):
    ticker: str
    quantity: int
    entry_price: str
    entry_date: str


class UserDetail(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    is_active: bool


class UserInspectorResponse(BaseModel):
    user: UserDetail
    account: AccountDetail
    positions: list[PositionDetail]


class FundRequest(BaseModel):
    # Decimal string in, per architecture 5/assumption 5. Pydantic v2
    # coerces a numeric-looking str straight to Decimal.
    amount: decimal.Decimal

    @field_validator("amount")
    @classmethod
    def _validate_amount(cls, v: decimal.Decimal) -> decimal.Decimal:
        if v <= 0:
            raise ValueError("amount must be > 0")
        return v


class FundResponse(BaseModel):
    new_balance: str
