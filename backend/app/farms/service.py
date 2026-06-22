import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.farms.models import Farm
from app.farms.schemas import FarmCreate, FarmUpdate


import re

async def generate_unique_slug(db: AsyncSession, name: str, base_slug: str | None = None) -> str:
    if base_slug:
        raw_slug = base_slug.strip().lower()
    else:
        raw_slug = name.strip().lower()
    
    # collapse consecutive whitespace/hyphens and remove special characters
    cleaned = re.sub(r"[^\w\s-]", "", raw_slug)
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned)
    slug = cleaned.strip("-")
    
    if not slug:
        slug = "farm"

    final_slug = slug
    counter = 1
    while True:
        result = await db.execute(select(Farm).where(Farm.slug == final_slug))
        if not result.scalar_one_or_none():
            break
        final_slug = f"{slug}-{counter}"
        counter += 1
        
    return final_slug


async def create_farm(db: AsyncSession, data: FarmCreate) -> Farm:
    slug = await generate_unique_slug(db, data.name, data.slug)
    farm = Farm(
        name=data.name,
        location=data.location,
        slug=slug,
    )
    db.add(farm)
    await db.commit()
    await db.refresh(farm)
    return farm


async def get_farm(db: AsyncSession, farm_id: str) -> Farm | None:
    result = await db.execute(select(Farm).where(Farm.id == farm_id))
    return result.scalar_one_or_none()


async def list_farms(db: AsyncSession) -> list[Farm]:
    result = await db.execute(select(Farm).order_by(Farm.name))
    return result.scalars().all()


async def update_farm(db: AsyncSession, farm_id: str, data: FarmUpdate) -> Farm | None:
    result = await db.execute(select(Farm).where(Farm.id == farm_id))
    farm = result.scalar_one_or_none()
    if not farm:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(farm, key, value)
    await db.commit()
    await db.refresh(farm)
    return farm


async def delete_farm(db: AsyncSession, farm_id: str) -> bool:
    result = await db.execute(select(Farm).where(Farm.id == farm_id))
    farm = result.scalar_one_or_none()
    if not farm:
        return False

    from app.auth.models import User
    from app.cameras.models import Camera
    from app.chickens.models import Chicken
    from sqlalchemy import func

    has_users = (await db.execute(select(func.count(User.id)).where(User.farm_id == farm_id))).scalar_one() > 0
    has_cameras = (await db.execute(select(func.count(Camera.id)).where(Camera.farm_id == farm_id))).scalar_one() > 0
    has_chickens = (await db.execute(select(func.count(Chicken.id)).where(Chicken.farm_id == farm_id))).scalar_one() > 0

    if has_users or has_cameras or has_chickens:
        deps = []
        if has_users: deps.append("users")
        if has_cameras: deps.append("cameras")
        if has_chickens: deps.append("chickens")
        raise ValueError(f"Cannot delete farm because it has associated {', '.join(deps)}")

    await db.delete(farm)
    await db.commit()
    return True
