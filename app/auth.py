"""
JWT-based authentication for Sepsis Watch API.

Flow:
  1. POST /auth/token  { username, password }  → { access_token, token_type }
  2. Include header:   Authorization: Bearer <access_token>
  3. Protected routes call Depends(get_current_user) automatically.

Supported authentication modes:
  - Username/password login (hashed with bcrypt, stored in APIUser table)
  - API key header  X-API-Key: <key>   (for services and testing)

Public endpoints (no token required):
  - GET  /health
  - POST /auth/token
  - GET  /docs, /redoc, /openapi.json
  - POST /webhooks/*  (Twilio delivery receipts — authenticated by Twilio signature instead)
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.db.base import Base, get_db

# ── Constants ─────────────────────────────────────────────────────────────────

SECRET_KEY: str = os.getenv("SECRET_KEY", "INSECURE_DEV_KEY_CHANGE_ME")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hours — one clinical shift

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── DB model ──────────────────────────────────────────────────────────────────

class APIUser(Base):
    """Stores hashed credentials for dashboard / service accounts."""
    __tablename__ = "api_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    full_name = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    api_key = Column(String(64), unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Token helpers ─────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ── FastAPI dependency: get_current_user ──────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> APIUser:
    """
    Resolves a request to an APIUser via either:
      - Authorization: Bearer <jwt>
      - X-API-Key: <key>

    Raises 401 if neither is present or valid.
    """
    # ── Path 1: API Key ───────────────────────────────────────────────────
    if api_key:
        result = await db.execute(
            select(APIUser).where(APIUser.api_key == api_key, APIUser.is_active == True)
        )
        user = result.scalar_one_or_none()
        if user:
            return user

    # ── Path 2: Bearer JWT ────────────────────────────────────────────────
    if credentials:
        token = credentials.credentials
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: Optional[str] = payload.get("sub")
            if username is None:
                raise _credentials_error()
        except JWTError:
            raise _credentials_error()

        result = await db.execute(
            select(APIUser).where(APIUser.username == username, APIUser.is_active == True)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise _credentials_error()
        return user

    raise _credentials_error()


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated — provide Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )
