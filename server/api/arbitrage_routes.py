import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from ..auth import CurrentUser, get_current_user
from ..db import get_redis

router = APIRouter(prefix="/api/v1/arbitrage", tags=["Arbitrage"])


@router.get("/opportunities")
async def list_opportunities(
    type: Literal["triangular", "cashcarry"] = "triangular",
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be > 0")
    if limit > 200:
        limit = 200

    key = f"opportunities:{type}"
    redis = await get_redis()

    rows = await redis.zrevrange(key, 0, limit - 1, withscores=True)
    result = []

    for member, score in rows:
        try:
            payload = json.loads(member)
        except Exception:
            payload = {"raw": member}

        if isinstance(payload, dict):
            payload["score"] = float(score)
        result.append(payload)

    return {
        "type": type,
        "limit": limit,
        "items": result,
    }


@router.post("/opportunities/clear")
async def clear_opportunities(
    type: Literal["triangular", "cashcarry", "all"] = "all",
    user: CurrentUser = Depends(get_current_user),
):
    """
    清空套利机会缓存（Redis）
    """
    redis = await get_redis()
    if type == "all":
        keys = ["opportunities:triangular", "opportunities:cashcarry"]
    else:
        keys = [f"opportunities:{type}"]
    deleted = await redis.delete(*keys)
    return {"message": "机会已清空", "deleted": deleted, "type": type}
