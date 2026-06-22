from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_permission
from app.auth.models import User
from app.database import get_db
from app.farms.models import Farm
from app.farms.schemas import FarmCreate, FarmOut, FarmUpdate
from app.farms.service import create_farm, delete_farm, get_farm, list_farms, update_farm
from app.rate_limit import limiter

router = APIRouter(prefix="/farms", tags=["farms"])


@router.get("", response_model=list[FarmOut])
async def get_farms(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role.name == "super_admin":
        return await list_farms(db)
    if user.farm_id:
        farm = await get_farm(db, str(user.farm_id))
        return [farm] if farm else []
    return []


@router.get("/{farm_id}", response_model=FarmOut)
async def get_farm_detail(
    farm_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role.name != "super_admin":
        if user.farm_id is None or str(user.farm_id) != farm_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    farm = await get_farm(db, farm_id)
    if not farm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")
    return farm


@router.post("", response_model=FarmOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def add_farm(
    request: Request,
    data: FarmCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("system:audit")),
):
    if user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return await create_farm(db, data)


@router.put("/{farm_id}", response_model=FarmOut)
@limiter.limit("20/minute")
async def edit_farm(
    farm_id: str,
    request: Request,
    data: FarmUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("system:audit")),
):
    if user.role.name != "super_admin":
        if user.farm_id is None or str(user.farm_id) != farm_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    farm = await update_farm(db, farm_id, data)
    if not farm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")
    return farm


@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def remove_farm(
    farm_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("system:audit")),
):
    if user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    try:
        deleted = await delete_farm(db, farm_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
