from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user, get_farm_id, require_permission
from app.auth.models import User
from app.cameras.models import Camera
from app.cameras.schemas import CameraOut
from app.coops.models import Coop
from app.coops.schemas import CoopCreate, CoopOut, CoopUpdate
from app.database import get_db
from app.rate_limit import limiter

router = APIRouter(prefix="/coops", tags=["coops"])


def _enrich_camera(camera: Camera) -> CameraOut:
    cam_out = CameraOut.model_validate(camera)
    cam_out.hls_url = f"/api/frigate/hls/{camera.name}/index.m3u8"
    return cam_out


@router.get("", response_model=list[CoopOut])
async def list_coops(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    farm_id: str | None = Depends(get_farm_id),
):
    query = select(Coop).order_by(Coop.sort_order, Coop.name)
    if farm_id:
        query = query.where(Coop.farm_id == farm_id)
    result = await db.execute(query)
    coops = result.scalars().all()

    camera_query = select(Camera)
    if farm_id:
        camera_query = camera_query.where(Camera.farm_id == farm_id)
    cameras_result = await db.execute(camera_query)
    all_cameras = cameras_result.scalars().all()

    coop_map: dict[str, list[Camera]] = {}
    for cam in all_cameras:
        key = str(cam.coop_id) if cam.coop_id else "__unassigned"
        coop_map.setdefault(key, []).append(cam)

    result_list: list[CoopOut] = []
    for coop in coops:
        cameras = coop_map.get(str(coop.id), [])
        result_list.append(CoopOut(
            id=coop.id,
            name=coop.name,
            sort_order=coop.sort_order,
            created_at=coop.created_at,
            cameras=[_enrich_camera(c) for c in sorted(cameras, key=lambda x: x.name or "")],
        ))

    unassigned = coop_map.get("__unassigned", [])
    if unassigned:
        result_list.append(CoopOut(
            id=UUID("00000000-0000-0000-0000-000000000000"),
            name="Unassigned",
            sort_order=9999,
            created_at=datetime.now(timezone.utc),
            cameras=[_enrich_camera(c) for c in sorted(unassigned, key=lambda x: x.name or "")],
        ))

    return result_list


@router.post("", response_model=CoopOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_coop(
    request: Request,
    data: CoopCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    if not farm_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="farm_id required")
    coop = Coop(name=data.name, sort_order=data.sort_order, farm_id=farm_id)
    db.add(coop)
    await db.commit()
    await db.refresh(coop)
    return CoopOut(
        id=coop.id,
        name=coop.name,
        sort_order=coop.sort_order,
        created_at=coop.created_at,
        cameras=[],
    )


@router.put("/{coop_id}", response_model=CoopOut)
@limiter.limit("20/minute")
async def update_coop(
    coop_id: str,
    request: Request,
    data: CoopUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    result = await db.execute(select(Coop).where(Coop.id == coop_id))
    coop = result.scalar_one_or_none()
    if not coop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coop not found")
    if farm_id and str(coop.farm_id) != farm_id and (not user.role or user.role.name != "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if data.name is not None:
        coop.name = data.name
    if data.sort_order is not None:
        coop.sort_order = data.sort_order
    await db.commit()
    await db.refresh(coop)

    camera_query = select(Camera).where(Camera.coop_id == coop.id)
    cameras_result = await db.execute(camera_query)
    cameras = cameras_result.scalars().all()

    return CoopOut(
        id=coop.id,
        name=coop.name,
        sort_order=coop.sort_order,
        created_at=coop.created_at,
        cameras=[_enrich_camera(c) for c in sorted(cameras, key=lambda x: x.name or "")],
    )


@router.delete("/{coop_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_coop(
    coop_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    result = await db.execute(select(Coop).where(Coop.id == coop_id))
    coop = result.scalar_one_or_none()
    if not coop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coop not found")
    if farm_id and str(coop.farm_id) != farm_id and (not user.role or user.role.name != "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await db.execute(Camera.__table__.update().where(Camera.coop_id == coop.id).values(coop_id=None))
    await db.delete(coop)
    await db.commit()
