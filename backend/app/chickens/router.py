from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_permission
from app.auth.models import User
from app.chickens.schemas import ChickenCreate, ChickenOut, ChickenUpdate, DetectedChicken
from app.chickens.service import create_chicken, delete_chicken, get_chicken, list_chickens, update_chicken
from app.database import get_db

router = APIRouter(prefix="/chickens", tags=["chickens"])


@router.get("", response_model=list[ChickenOut])
async def get_chickens(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("chickens:read")),
):
    return await list_chickens(db)


@router.get("/detected", response_model=list[DetectedChicken])
async def get_detected_chickens(
    start: str = Query("-1h"),
    end: str = Query("now()"),
    user: User = Depends(require_permission("chickens:read")),
):
    try:
        from app.detection.queries import query_detected_chickens

        results = query_detected_chickens(start, end)
        return [DetectedChicken(**r) for r in results]
    except ImportError:
        return []
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Detection query failed: {e}")


@router.get("/{chicken_id}", response_model=ChickenOut)
async def get_chicken_detail(
    chicken_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("chickens:read")),
):
    chicken = await get_chicken(db, chicken_id)
    if not chicken:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chicken not found")
    return chicken


@router.post("", response_model=ChickenOut, status_code=status.HTTP_201_CREATED)
async def add_chicken(
    data: ChickenCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("chickens:write")),
):
    return await create_chicken(db, data)


@router.put("/{chicken_id}", response_model=ChickenOut)
async def edit_chicken(
    chicken_id: str,
    data: ChickenUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("chickens:write")),
):
    chicken = await update_chicken(db, chicken_id, data)
    if not chicken:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chicken not found")
    return chicken


@router.delete("/{chicken_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_chicken(
    chicken_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("chickens:write")),
):
    deleted = await delete_chicken(db, chicken_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chicken not found")


@router.post("/{chicken_id}/link-identity")
async def link_identity(
    chicken_id: str,
    global_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("chickens:write")),
):
    from sqlalchemy import select
    from app.chickens.models import Chicken

    result = await db.execute(select(Chicken).where(Chicken.id == chicken_id))
    chicken = result.scalar_one_or_none()
    if not chicken:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chicken not found")

    existing = await db.execute(
        select(Chicken).where(Chicken.global_id == global_id, Chicken.id != chicken_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Global ID {global_id} is already linked to another chicken",
        )

    chicken.global_id = global_id
    await db.commit()
    await db.refresh(chicken)
    return ChickenOut.model_validate(chicken)
