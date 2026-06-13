from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


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


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    role: RoleOut
    is_active: bool
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


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
