"""
Authentication endpoints.

POST /auth/token       — login with username+password, get JWT
POST /auth/users       — create API user (admin only)
GET  /auth/users/me    — get current user info
POST /auth/setup       — first-time bootstrap (creates admin if no users exist)
"""
import secrets
from datetime import timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    APIUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.base import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRE_MINUTES * 60


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    is_admin: bool = False


class UserResponse(BaseModel):
    id: UUID
    username: str
    full_name: Optional[str]
    is_active: bool
    is_admin: bool
    api_key: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = "Administrator"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/token", response_model=TokenResponse, summary="Login and get JWT")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange username + password for a JWT access token.
    The token is valid for 8 hours (one clinical shift).

    Use the token in all subsequent requests:
    `Authorization: Bearer <access_token>`
    """
    result = await db.execute(
        select(APIUser).where(APIUser.username == form_data.username)
    )
    user: Optional[APIUser] = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(access_token=token)


@router.post("/setup", response_model=UserResponse, status_code=201, summary="First-run admin setup")
async def setup_admin(
    payload: SetupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    One-time bootstrap: creates the first admin user.
    Fails with 409 if any user already exists — use /auth/users after that.
    """
    existing = await db.execute(select(APIUser).limit(1))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Setup already complete. Use POST /auth/users (admin only).",
        )

    user = APIUser(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_admin=True,
        api_key=secrets.token_hex(32),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/users/me", response_model=UserResponse, summary="Current user info")
async def get_me(current_user: APIUser = Depends(get_current_user)):
    return current_user


@router.post("/users", response_model=UserResponse, status_code=201, summary="Create API user (admin)")
async def create_user(
    payload: UserCreate,
    current_user: APIUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API user. Only admins can create users."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")

    existing = await db.execute(
        select(APIUser).where(APIUser.username == payload.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = APIUser(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_admin=payload.is_admin,
        api_key=secrets.token_hex(32),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
