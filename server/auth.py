import secrets
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException

from .db import get_pg_pool, get_redis


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    username: str
    email: Optional[str]
    role: str


SESSION_TTL_SECONDS = 60 * 60 * 24 * 7


async def create_session(user_id: UUID) -> str:
    token = secrets.token_urlsafe(32)
    redis = await get_redis()
    await redis.set(f"session:{token}", str(user_id), ex=SESSION_TTL_SECONDS)
    return token


async def delete_session(token: str) -> None:
    redis = await get_redis()
    await redis.delete(f"session:{token}")


async def get_current_user_from_token(token: str) -> CurrentUser:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    redis = await get_redis()
    user_id_str = await redis.get(f"session:{token}")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Session expired")

    if isinstance(user_id_str, (bytes, bytearray)):
        user_id_str = user_id_str.decode("utf-8")

    try:
        user_id = UUID(user_id_str)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")

    pool = await get_pg_pool()
    row = await pool.fetchrow(
        "SELECT id, username, email, COALESCE(role, 'user') AS role FROM users WHERE id = $1 AND is_active = true",
        user_id,
    )
    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return CurrentUser(id=row["id"], username=row["username"], email=row["email"], role=row["role"])


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    redis = await get_redis()
    user_id_str = await redis.get(f"session:{token}")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Session expired")

    if isinstance(user_id_str, (bytes, bytearray)):
        user_id_str = user_id_str.decode("utf-8")

    try:
        user_id = UUID(user_id_str)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")

    pool = await get_pg_pool()
    row = await pool.fetchrow(
        "SELECT id, username, email, COALESCE(role, 'user') AS role FROM users WHERE id = $1 AND is_active = true",
        user_id,
    )
    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return CurrentUser(id=row["id"], username=row["username"], email=row["email"], role=row["role"])


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
