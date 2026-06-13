from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.auth.models import Role, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

BLACKLISTED_TOKENS: set[str] = set()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role_name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "role": role_name, "exp": expire, "type": "access"}
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


def blacklist_token(token: str):
    BLACKLISTED_TOKENS.add(token)


def is_token_blacklisted(token: str) -> bool:
    return token in BLACKLISTED_TOKENS


PERMISSION_MAP = {
    "viewer": [
        "dashboard:read", "live:read", "chickens:read", "cameras:read",
        "analytics:read",
    ],
    "operator": [
        "dashboard:read", "live:read", "chickens:read", "chickens:write",
        "cameras:read", "cameras:write", "cameras:scan",
        "analytics:read",
    ],
    "admin": [
        "dashboard:read", "live:read", "chickens:read", "chickens:write",
        "cameras:read", "cameras:write", "cameras:scan", "cameras:delete",
        "users:read", "users:write", "settings:read", "settings:write",
        "analytics:read",
    ],
    "super_admin": [
        "dashboard:read", "live:read", "chickens:read", "chickens:write",
        "cameras:read", "cameras:write", "cameras:scan", "cameras:delete",
        "users:read", "users:write", "settings:read", "settings:write",
        "system:audit", "system:backup", "roles:write",
        "analytics:read",
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


async def seed_super_admin(db: AsyncSession):
    result = await db.execute(select(User).where(User.email == "admin@poultry.farm"))
    if not result.scalar_one_or_none():
        role_result = await db.execute(select(Role).where(Role.name == "super_admin"))
        role = role_result.scalar_one_or_none()
        if role:
            user = User(
                email="admin@poultry.farm",
                hashed_password=hash_password("admin123"),
                full_name="Super Admin",
                role_id=role.id,
                is_active=True,
            )
            db.add(user)
