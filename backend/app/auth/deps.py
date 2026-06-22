from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import Role, User
from app.auth.service import decode_token, is_token_blacklisted
from app.database import get_db


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth[7:]
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    if await is_token_blacklisted(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token blacklisted")

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.id == payload["sub"])
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


def require_permission(permission: str):
    async def checker(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
        role_result = await db.execute(select(Role).where(Role.id == user.role_id))
        role = role_result.scalar_one_or_none()
        if not role or permission not in role.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return user
    return checker


async def get_farm_id(
    user: User = Depends(get_current_user),
    x_farm_id: str | None = Header(None, alias="X-Farm-ID"),
    farm_id: str | None = Query(None, description="Farm ID for super_admin to scope data"),
    db: AsyncSession = Depends(get_db),
) -> str | None:
    if user.role.name == "super_admin":
        candidate = x_farm_id or farm_id or (str(user.farm_id) if user.farm_id else None)
    else:
        candidate = str(user.farm_id) if user.farm_id else None

    if candidate:
        try:
            UUID(candidate)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid farm ID format")
        
        from app.farms.models import Farm
        result = await db.execute(select(Farm).where(Farm.id == candidate))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")

    return candidate
