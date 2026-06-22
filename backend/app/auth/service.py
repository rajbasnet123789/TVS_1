import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from jose import ExpiredSignatureError, JWTError, jwt

logger = logging.getLogger(__name__)
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.auth.models import Role, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

BLACKLISTED_TOKENS: set[str] = set()
USED_REFRESH_TOKENS: set[str] = set()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: str,
    role_name: str,
    farm_id: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "role": role_name, "farm_id": farm_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except (JWTError, ExpiredSignatureError):
        return None


from typing import Optional

redis_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(settings.redis_url)
    return redis_client


async def close_redis():
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None


async def blacklist_token(token: str):
    try:
        r = get_redis()
        await r.setex(f"bl:{token}", settings.access_token_expire_minutes * 60, "1")
    except Exception:
        logger.exception("Redis error while blacklisting token: %s", token)
        BLACKLISTED_TOKENS.add(token)


async def is_token_blacklisted(token: str) -> bool:
    try:
        r = get_redis()
        exists = await r.exists(f"bl:{token}")
        if exists:
            return True
    except Exception:
        logger.exception("Redis error while checking if token is blacklisted: %s", token)
    return token in BLACKLISTED_TOKENS


async def is_refresh_token_used(token: str) -> bool:
    try:
        r = get_redis()
        exists = await r.exists(f"rtu:{token}")
        if exists:
            return True
    except Exception:
        logger.exception("Redis error while checking if refresh token is used: %s", token)
    return token in USED_REFRESH_TOKENS


async def mark_refresh_token_used(token: str):
    try:
        r = get_redis()
        await r.setex(f"rtu:{token}", settings.refresh_token_expire_days * 86400, "1")
    except Exception:
        logger.exception("Redis error while marking refresh token as used: %s", token)
        USED_REFRESH_TOKENS.add(token)


PERMISSION_MAP = {
    "viewer": [
        "dashboard:read", "live:read", "chickens:read", "cameras:read",
        "analytics:read", "nvr:read",
    ],
    "operator": [
        "dashboard:read", "live:read", "chickens:read", "chickens:write",
        "cameras:read", "cameras:write",
        "analytics:read", "nvr:read",
    ],
    "admin": [
        "dashboard:read", "live:read", "chickens:read", "chickens:write",
        "cameras:read", "cameras:write", "cameras:scan", "cameras:delete",
        "users:read", "users:write", "settings:read", "settings:write",
        "analytics:read", "nvr:read",
    ],
    "super_admin": [
        "dashboard:read", "live:read", "chickens:read", "chickens:write",
        "cameras:read", "cameras:write", "cameras:scan", "cameras:delete",
        "users:read", "users:write", "users:impersonate",
        "settings:read", "settings:write",
        "system:audit", "system:backup", "roles:write",
        "analytics:read", "nvr:read",
    ],
}


async def seed_roles(db: AsyncSession):
    for role_name, perms in PERMISSION_MAP.items():
        result = await db.execute(select(Role).where(Role.name == role_name))
        existing = result.scalar_one_or_none()
        if not existing:
            role = Role(name=role_name, permissions=perms, description=f"{role_name.replace('_', ' ').title()} role")
            db.add(role)
        elif set(existing.permissions) != set(perms):
            existing.permissions = perms
            db.add(existing)


async def seed_default_farm(db: AsyncSession):
    from app.farms.models import Farm
    import uuid
    result = await db.execute(select(Farm).where(Farm.slug == "default"))
    farm = result.scalar_one_or_none()
    if not farm:
        farm = Farm(
            id=uuid.UUID('00000000-0000-0000-0000-000000000001'),
            name="Default Farm",
            location="Main Location",
            slug="default",
            settings={},
            is_active=True,
        )
        db.add(farm)
        await db.flush()
        await db.refresh(farm)
        logger.info("Default farm created")
    return farm


async def seed_super_admin(db: AsyncSession):
    role_result = await db.execute(select(Role).where(Role.name == "super_admin"))
    role = role_result.scalar_one_or_none()
    if not role:
        logger.warning("seed_super_admin: super_admin role not found — skipping admin user creation")
        return

    admin_password = settings.default_admin_password
    result = await db.execute(select(User).where(User.email == "admin@poultry.farm"))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            email="admin@poultry.farm",
            hashed_password=hash_password(admin_password),
            full_name="Super Admin",
            role_id=role.id,
            is_active=True,
            farm_id=None,
            must_change_password=True,
        )
        db.add(user)
        logger.info(f"Default super_admin created (admin@poultry.farm) with configured password")
    elif not user.hashed_password:
        user.hashed_password = hash_password(admin_password)
        db.add(user)
        logger.info(f"Default super_admin (admin@poultry.farm) password set during initial setup")
