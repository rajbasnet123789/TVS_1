from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chickens.models import Chicken
from app.chickens.schemas import ChickenCreate, ChickenUpdate


async def create_chicken(db: AsyncSession, data: ChickenCreate, farm_id: str) -> Chicken:
    chicken = Chicken(
        chicken_id=data.chicken_id,
        name=data.name,
        breed=data.breed,
        notes=data.notes,
        farm_id=farm_id,
    )
    db.add(chicken)
    await db.commit()
    await db.refresh(chicken)
    return chicken


async def update_chicken(db: AsyncSession, chicken_id: str, data: ChickenUpdate) -> Chicken | None:
    result = await db.execute(select(Chicken).where(Chicken.id == chicken_id))
    chicken = result.scalar_one_or_none()
    if not chicken:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(chicken, key, value)
    await db.commit()
    await db.refresh(chicken)
    return chicken


async def delete_chicken(db: AsyncSession, chicken_id: str) -> bool:
    result = await db.execute(select(Chicken).where(Chicken.id == chicken_id))
    chicken = result.scalar_one_or_none()
    if not chicken:
        return False
    await db.delete(chicken)
    await db.commit()
    return True


async def get_chicken(db: AsyncSession, chicken_id: str) -> Chicken | None:
    result = await db.execute(select(Chicken).where(Chicken.id == chicken_id))
    return result.scalar_one_or_none()


async def list_chickens(db: AsyncSession, farm_id: str | None = None) -> list[Chicken]:
    query = select(Chicken)
    if farm_id:
        query = query.where(Chicken.farm_id == farm_id)
    result = await db.execute(query.order_by(Chicken.chicken_id))
    return result.scalars().all()
