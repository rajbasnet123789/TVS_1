import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


_PASSWORD_RE = re.compile(r"^.{10,}$")


def _validate_password(v: str) -> str:
    if len(v) < 10:
        raise ValueError("Password must be at least 10 characters long")
    
    errors = []
    if not re.search(r"[A-Z]", v):
        errors.append("an uppercase letter")
    if not re.search(r"[a-z]", v):
        errors.append("a lowercase letter")
    if not re.search(r"\d", v):
        errors.append("a number")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
        errors.append("a special character")
        
    if errors:
        raise ValueError(f"Password must contain: {', '.join(errors)}")
    return v



class RoleOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    permissions: list

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role_name: str = "viewer"
    farm_id: UUID | None = None

    _validate_password = field_validator("password")(_validate_password)


class UserUpdate(BaseModel):
    role_name: str | None = None
    farm_id: UUID | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    role: RoleOut
    farm_id: UUID | None
    is_active: bool
    must_change_password: bool
    last_login: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool


class TokenRefreshRequest(BaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    _validate_new_password = field_validator("new_password")(_validate_password)


class GoogleLoginRequest(BaseModel):
    credential: str


class AuthConfigResponse(BaseModel):
    google_client_id: str | None = None
