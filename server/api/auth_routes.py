from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUser, create_session, delete_session, get_current_user
from ..db import get_pg_pool

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    oldPassword: str
    newPassword: str


@router.post("/login")
async def login(payload: LoginRequest):
    pool = await get_pg_pool()

    row = await pool.fetchrow(
        """
        SELECT id, username, email, COALESCE(role, 'user') AS role
        FROM users
        WHERE username = $1 AND is_active = true
        """,
        payload.username,
    )

    if not row:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    ok = await pool.fetchval(
        """
        SELECT password_hash = crypt($1, password_hash)
        FROM users
        WHERE id = $2
        """,
        payload.password,
        row["id"],
    )

    if not ok:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = await create_session(row["id"])

    return {
        "success": True,
        "token": token,
        "user": {
            "id": str(row["id"]),
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
        },
    }


@router.post("/logout")
async def logout(
    user: CurrentUser = Depends(get_current_user),
    authorization: Optional[str] = Header(default=None),
):
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
        if token:
            await delete_session(token)

    return {"success": True}


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    return {
        "success": True,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
        },
    }


@router.patch("/profile")
async def update_profile(
    payload: UpdateProfileRequest,
    user: CurrentUser = Depends(get_current_user),
):
    pool = await get_pg_pool()

    new_username = (payload.username or "").strip() or None
    new_email = (payload.email or "").strip() or None

    if new_username:
        exists = await pool.fetchval(
            "SELECT 1 FROM users WHERE username = $1 AND id <> $2",
            new_username,
            user.id,
        )
        if exists:
            raise HTTPException(status_code=409, detail="Username already exists")

    row = await pool.fetchrow(
        """
        UPDATE users
        SET username = COALESCE($1, username),
            email = COALESCE($2, email),
            updated_at = NOW()
        WHERE id = $3
        RETURNING id, username, email, COALESCE(role, 'user') AS role
        """,
        new_username,
        new_email,
        user.id,
    )

    return {
        "success": True,
        "user": {
            "id": str(row["id"]),
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
        },
    }


@router.post("/password")
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser = Depends(get_current_user),
):
    pool = await get_pg_pool()

    ok = await pool.fetchval(
        """
        SELECT password_hash = crypt($1, password_hash)
        FROM users
        WHERE id = $2
        """,
        payload.oldPassword,
        user.id,
    )

    if not ok:
        raise HTTPException(status_code=400, detail="Invalid current password")

    await pool.execute(
        """
        UPDATE users
        SET password_hash = crypt($1, gen_salt('bf')),
            updated_at = NOW()
        WHERE id = $2
        """,
        payload.newPassword,
        user.id,
    )

    return {"success": True}
