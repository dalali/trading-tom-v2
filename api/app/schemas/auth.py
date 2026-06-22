"""Pydantic v2 request/response schemas for /auth/* (architecture 5.1).

No money fields in this slice.

Assumption: email is validated as a plain non-empty `str`, not
pydantic's `EmailStr`, because that requires the optional
`email-validator` package which is not in requirements.txt. Login
also intentionally does not 400 on a malformed email — it falls
through to the generic 401 "Invalid email or password" so failed
login attempts can't be used to probe email-format vs. existence
(architecture 9.1 account-enumeration resistance).
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    role: str
    user_id: int


class RefreshResponse(BaseModel):
    access_token: str


class MeResponse(BaseModel):
    user_id: int
    email: str
    display_name: str
    role: str
    is_active: bool
