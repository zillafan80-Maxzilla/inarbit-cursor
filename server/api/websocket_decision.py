import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from ..db import get_redis

logger = logging.getLogger(__name__)


async def verify_token(token: str) -> Optional[str]:
    """复用 websocket.py 的 token 验证逻辑"""
    try:
        from ..auth import get_current_user_from_token
        user = await get_current_user_from_token(token)
        return str(user.id) if user else None
    except Exception:
        return None


async def decision_websocket_endpoint(
    websocket: WebSocket,
    token: str,
    interval: float = 1.0,
    limit: int = 10,
):
    """推送决策器输出的决策列表（带避险约束过滤后的结果）"""
    # 验证 token
    user_id = await verify_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    channel = f"decision:{user_id}"
    logger.info(f"WebSocket 连接已建立: {channel}")

    try:
        while True:
            redis = await get_redis()
            members = await redis.zrange("decisions:latest", 0, limit - 1, withscores=True)
            decisions = []
            for member, score in members:
                try:
                    data = json.loads(member)
                    decisions.append(data)
                except Exception:
                    continue

            payload = {
                "type": "decisions",
                "timestamp": int(time.time() * 1000),
                "data": decisions,
                "count": len(decisions),
            }
            await websocket.send_text(json.dumps(payload, ensure_ascii=False, default=str))
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        logger.info(f"WebSocket 连接已断开: {channel}")
    except Exception as e:
        logger.exception(f"Decision WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason="internal_error")
        except Exception:
            pass
