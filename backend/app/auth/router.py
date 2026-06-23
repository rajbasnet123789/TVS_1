import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta

from app.auth.deps import get_current_user, get_farm_id, require_permission
from app.auth.models import Role, User
from app.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserCreate,
    UserOut,
    AuthConfigResponse,
    GoogleLoginRequest,
)
from app.auth.service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    blacklist_token,
    is_refresh_token_used,
    mark_refresh_token_used,
    PERMISSION_MAP,
)
from app.config import settings
from app.database import get_db
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

security = HTTPBearer(auto_error=False)


@router.get("/validate-token", include_in_schema=False)
async def validate_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = None
    if credentials:
        token = credentials.credentials
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No token provided")
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return {"valid": True, "sub": payload.get("sub")}


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        secure=settings.cookies_secure,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
        secure=settings.cookies_secure,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour")
async def register(
    request: Request,
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_permission("users:write")),
):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    role_result = await db.execute(select(Role).where(Role.name == data.role_name))
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Role '{data.role_name}' not found")

    if data.role_name == "super_admin":
        existing = await db.execute(select(User).where(User.role_id == role.id))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A super admin already exists. Only one super admin is allowed.",
            )
    target_farm_id = data.farm_id or (str(admin_user.farm_id) if admin_user.farm_id else None)
    if role.name != "super_admin" and not target_farm_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="farm_id required for non-super_admin users",
        )
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role_id=role.id,
        farm_id=target_farm_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user.role = role
    user.farm_id = str(user.farm_id) if user.farm_id else None
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, response: Response, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one_or_none()

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    farm_id = str(user.farm_id) if user.farm_id else None
    access_token = create_access_token(str(user.id), role.name if role else "viewer", farm_id=farm_id)
    refresh_token = create_refresh_token(str(user.id))
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        must_change_password=user.must_change_password
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh(request: Request, response: Response, data: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    token = data.refresh_token or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")

    payload = decode_token(token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if await is_refresh_token_used(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token already used — possible token theft. Please log in again.",
        )

    await mark_refresh_token_used(token)

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one_or_none()

    farm_id = str(user.farm_id) if user.farm_id else None
    access_token = create_access_token(str(user.id), role.name if role else "viewer", farm_id=farm_id)
    refresh_token = create_refresh_token(str(user.id))
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


security_scheme = HTTPBearer(auto_error=False)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
):
    auth_header = request.headers.get("authorization")
    token = credentials.credentials if credentials is not None else request.cookies.get("access_token") or (
        auth_header[7:] if auth_header and auth_header.lower().startswith("bearer ") else None
    )
    if token:
        await blacklist_token(token)
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.old_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = False
    await db.commit()
    return {"message": "Password changed successfully"}


@router.post("/impersonate/{user_id}")
async def impersonate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("users:impersonate")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target or not target.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or inactive")
    role_result = await db.execute(select(Role).where(Role.id == target.role_id))
    role = role_result.scalar_one_or_none()
    farm_id = str(target.farm_id) if target.farm_id else None
    token = create_access_token(
        str(target.id),
        role.name if role else "viewer",
        farm_id=farm_id,
        expires_delta=timedelta(seconds=900),
    )
    return {
        "access_token": token,
        "expires_in": 900,
        "impersonating": {
            "id": str(target.id),
            "email": target.email,
            "full_name": target.full_name,
            "role": role.name if role else "viewer",
            "permissions": role.permissions if role else [],
        },
    }


@router.get("/users", response_model=list[UserOut])
async def list_users(
    user: User = Depends(require_permission("users:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    query = select(User)
    if farm_id:
        query = query.where(User.farm_id == farm_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("users:write")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    role_result = await db.execute(select(Role).where(Role.id == target.role_id))
    target_role = role_result.scalar_one_or_none()
    if target_role and target_role.name == "super_admin":
        remaining = await db.execute(select(User).where(User.role_id == target.role_id, User.id != target.id))
        if not remaining.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Cannot delete the only super admin")
    elif user.role.name != "super_admin":
        if target.farm_id is None or str(target.farm_id) != str(user.farm_id):
            raise HTTPException(status_code=403, detail="Access denied")
    await db.delete(target)
    await db.commit()


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config():
    return AuthConfigResponse(google_client_id=settings.google_client_id or None)


@router.post("/google", response_model=TokenResponse)
async def login_google(data: GoogleLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google login is not configured on this server"
        )
    
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            google_response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": data.credential}
            )
            if google_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Google credential"
                )
            token_info = google_response.json()
    except Exception as e:
        logger.warning(f"Google token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to verify Google token"
        )
        
    if token_info.get("aud") != settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token audience mismatch"
        )
        
    if token_info.get("email_verified") != "true" and token_info.get("email_verified") != True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google email is not verified"
        )
        
    email = token_info.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No email found in Google token"
        )
        
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found. Please contact your administrator to create an account."
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )

    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one_or_none()

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    farm_id = str(user.farm_id) if user.farm_id else None
    access_token = create_access_token(str(user.id), role.name if role else "viewer", farm_id=farm_id)
    refresh_token = create_refresh_token(str(user.id))
    _set_auth_cookies(response, access_token, refresh_token)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        must_change_password=user.must_change_password
    )
