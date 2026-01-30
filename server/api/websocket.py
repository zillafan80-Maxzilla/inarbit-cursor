"""
WebSocket 实时推送
提供行情、信号、日志的实时订阅
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Set, Optional
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..db import get_redis
from ..services.order_service import PnLService
from ..auth import get_current_user_from_token
from ..services.config_service import get_config_service
from .websocket_decision import decision_websocket_endpoint

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # 按频道分组的活跃连接
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, channel: str):
        """接受新连接"""
        await websocket.accept()
        async with self._lock:
            if channel not in self.active_connections:
                self.active_connections[channel] = set()
            self.active_connections[channel].add(websocket)
        logger.info(f"WebSocket 连接已建立: {channel}")
    
    async def disconnect(self, websocket: WebSocket, channel: str):
        """断开连接"""
        async with self._lock:
            if channel in self.active_connections:
                self.active_connections[channel].discard(websocket)
        logger.info(f"WebSocket 连接已断开: {channel}")
    
    async def broadcast(self, channel: str, message: dict):
        """广播消息到指定频道"""
        if channel not in self.active_connections:
            return
        
        payload = json.dumps(message, default=str)
        dead_connections = set()
        
        for connection in self.active_connections[channel]:
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.add(connection)
        
        # 清理断开的连接
        for conn in dead_connections:
            self.active_connections[channel].discard(conn)


# 全局连接管理器
manager = ConnectionManager()


# ============================================
# WebSocket 端点
# ============================================

@router.websocket("/signals")
async def websocket_signals(websocket: WebSocket):
    """
    套利信号实时推送
    订阅类型: triangular, graph, funding_rate, grid, pair
    """
    token = websocket.query_params.get("token")
    try:
        user = await get_current_user_from_token(token or "")
    except HTTPException:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket, f"signals:{user.id}")
    
    redis_task = None
    pubsub = None
    try:
        # 启动 Redis 订阅
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.psubscribe(f"signal:{user.id}:*")
        
        async def listen_redis():
            async for message in pubsub.listen():
                if message['type'] == 'pmessage':
                    await websocket.send_text(message['data'])
        
        redis_task = asyncio.create_task(listen_redis())
        
        # 同时监听客户端消息 (心跳检测)
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), 
                    timeout=30
                )
                # 处理客户端消息 (如心跳 ping)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # 发送心跳
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        if redis_task:
            redis_task.cancel()
        if pubsub:
            await pubsub.punsubscribe(f"signal:{user.id}:*")
        await manager.disconnect(websocket, f"signals:{user.id}")


@router.websocket("/tickers/{exchange}")
async def websocket_tickers(websocket: WebSocket, exchange: str):
    """
    行情数据实时推送
    """
    token = websocket.query_params.get("token")
    try:
        user = await get_current_user_from_token(token or "")
    except HTTPException:
        await websocket.close(code=4401)
        return

    try:
        service = await get_config_service()
        ex = await service.get_exchange(exchange, user_id=user.id)
        if not ex or not ex.is_connected:
            logger.info(
                "WebSocket tickers rejected: user=%s exchange=%s reason=exchange_not_connected",
                user.id,
                exchange,
            )
            await websocket.close(code=4403, reason="exchange_not_connected")
            return
    except Exception:
        logger.exception("WebSocket tickers error before connect: user=%s exchange=%s", user.id, exchange)
        await websocket.close(code=1011, reason="internal_error")
        return

    channel = f"tickers:{exchange}"
    await manager.connect(websocket, channel)
    
    try:
        redis = await get_redis()
        try:
            limit = int(websocket.query_params.get("limit") or "200")
        except Exception:
            limit = 200
        if limit <= 0:
            limit = 200
        if limit > 200:
            limit = 200
        try:
            interval = float(websocket.query_params.get("interval") or "1")
        except Exception:
            interval = 1.0
        if interval < 0.2:
            interval = 0.2
        if interval > 10:
            interval = 10.0
        last_payload: Optional[str] = None
        
        while True:
            # 从 Redis 获取最新行情
            symbols = []
            cursor = 0
            index_key = f"symbols:ticker:{exchange}"
            while True:
                cursor, members = await redis.sscan(cursor=cursor, name=index_key, count=200)
                if members:
                    for m in members:
                        sym = m.decode() if isinstance(m, (bytes, bytearray)) else str(m)
                        symbols.append(sym)
                        if len(symbols) >= limit:
                            symbols = symbols[:limit]
                            break
                if len(symbols) >= limit or cursor == 0:
                    break

            keys = []
            if symbols:
                keys = [f"ticker:{exchange}:{sym}" for sym in symbols]
            else:
                cursor = 0
                pattern = f"ticker:{exchange}:*"
                while True:
                    cursor, batch = await redis.scan(cursor=cursor, match=pattern, count=200)
                    if batch:
                        keys.extend(batch)
                        if len(keys) >= limit:
                            keys = keys[:limit]
                            break
                    if cursor == 0:
                        break
            tickers = {}
            if keys:
                pipe = redis.pipeline()
                for key in keys:
                    pipe.hgetall(key)
                results = await pipe.execute()
                for key, data in zip(keys, results):
                    if data:
                        symbol = key.split(":")[-1]
                        tickers[symbol] = data
            
            if tickers:
                payload = json.dumps({
                    "type": "tickers",
                    "exchange": exchange,
                    "data": tickers
                })
                if payload != last_payload:
                    await websocket.send_text(payload)
                    last_payload = payload
            
            await asyncio.sleep(interval)  # 可配置更新频率
            
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, channel)


@router.websocket("/opportunities")
async def websocket_opportunities(websocket: WebSocket):
    token = websocket.query_params.get("token")
    try:
        user = await get_current_user_from_token(token or "")
    except HTTPException:
        await websocket.close(code=4401)
        return

    opp_type = websocket.query_params.get("type") or "triangular"
    try:
        limit = int(websocket.query_params.get("limit") or "50")
    except Exception:
        limit = 50
    if limit <= 0:
        limit = 50
    if limit > 200:
        limit = 200

    try:
        interval = float(websocket.query_params.get("interval") or "1")
    except Exception:
        interval = 1.0
    if interval < 0.2:
        interval = 0.2

    if opp_type not in {"triangular", "cashcarry"}:
        await websocket.close(code=4400, reason="invalid_type")
        return

    channel = f"opportunities:{user.id}:{opp_type}"
    await manager.connect(websocket, channel)

    try:
        redis = await get_redis()
        key = f"opportunities:{opp_type}"
        last_payload: Optional[str] = None

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=interval)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                pass

            rows = await redis.zrevrange(key, 0, limit - 1, withscores=True)
            items = []
            for member, score in rows:
                try:
                    payload = json.loads(member)
                except Exception:
                    payload = {"raw": member}
                if isinstance(payload, dict):
                    payload["score"] = float(score)
                items.append(payload)

            payload = json.dumps(
                {
                    "type": "opportunities",
                    "opportunityType": opp_type,
                    "limit": limit,
                    "data": items,
                },
                ensure_ascii=False,
                default=str,
            )
            if payload != last_payload:
                await websocket.send_text(payload)
                last_payload = payload

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, channel)


@router.websocket("/logs")
async def websocket_logs(websocket: WebSocket):
    """
    系统日志实时推送
    """
    token = websocket.query_params.get("token")
    try:
        user = await get_current_user_from_token(token or "")
    except HTTPException:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket, f"logs:{user.id}")
    
    pubsub = None
    try:
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.psubscribe(f"log:{user.id}:*")
        
        async for message in pubsub.listen():
            if message['type'] == 'pmessage':
                await websocket.send_text(message['data'])
                
    except WebSocketDisconnect:
        pass
    finally:
        if pubsub:
            await pubsub.punsubscribe(f"log:{user.id}:*")
        await manager.disconnect(websocket, f"logs:{user.id}")


@router.websocket("/orders")
async def websocket_orders(websocket: WebSocket):
    """
    订单状态实时推送
    """
    token = websocket.query_params.get("token")
    try:
        user = await get_current_user_from_token(token or "")
    except HTTPException:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket, f"orders:{user.id}")
    
    pubsub = None
    try:
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.psubscribe(f"order:{user.id}:*")
        
        async for message in pubsub.listen():
            if message['type'] == 'pmessage':
                await websocket.send_text(message['data'])
                
    except WebSocketDisconnect:
        pass
    finally:
        if pubsub:
            await pubsub.punsubscribe(f"order:{user.id}:*")
        await manager.disconnect(websocket, f"orders:{user.id}")


@router.websocket("/pnl")
async def websocket_pnl(
    websocket: WebSocket,
    trading_mode: str = Query("paper"),
    exchange_id: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    plan_id: Optional[str] = Query(None),
    created_after: Optional[str] = Query(None),
    created_before: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    interval: float = Query(1.0, ge=0.5, le=10.0),
):
    token = websocket.query_params.get("token")
    try:
        user = await get_current_user_from_token(token or "")
    except HTTPException:
        await websocket.close(code=4401)
        return

    channel = f"pnl:{user.id}"
    await manager.connect(websocket, channel)

    def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except Exception:
            return None

    dt_after = _parse_dt(created_after)
    dt_before = _parse_dt(created_before)
    last_payload: Optional[str] = None

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=interval)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                pass

            stats = await PnLService.get_statistics(user_id=user.id, trading_mode=trading_mode)
            total_profit = await PnLService.get_total_profit(user_id=user.id, trading_mode=trading_mode)
            summary = {
                **(stats or {}),
                "total_profit": float(total_profit),
            }
            rows = await PnLService.get_history(
                user_id=user.id,
                trading_mode=trading_mode,
                exchange_id=exchange_id,
                symbol=symbol,
                plan_id=plan_id,
                created_after=dt_after,
                created_before=dt_before,
                limit=limit,
                offset=offset,
            )
            payload = json.dumps(
                {
                    "type": "pnl",
                    "summary": summary,
                    "history": rows,
                    "timestamp": int(time.time() * 1000),
                },
                ensure_ascii=False,
                default=str,
            )
            if payload != last_payload:
                await websocket.send_text(payload)
                last_payload = payload
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, channel)


# ============================================
# 辅助函数 - 供其他模块调用发布消息
# ============================================

async def publish_signal(user_id: str, strategy_type: str, signal_data: dict):
    """发布套利信号"""
    redis = await get_redis()
    await redis.publish(
        f"signal:{user_id}:{strategy_type}",
        json.dumps(signal_data, default=str)
    )


async def publish_log(user_id: str, level: str, message: str, source: str = "system"):
    """发布系统日志"""
    redis = await get_redis()
    await redis.publish(
        f"log:{user_id}:{level.lower()}",
        json.dumps({
            "level": level,
            "source": source,
            "message": message
        })
    )


async def publish_order_update(user_id: str, order_id: str, status: str, data: dict):
    """发布订单状态更新"""
    redis = await get_redis()
    await redis.publish(
        f"order:{user_id}:{status}",
        json.dumps({
            "order_id": order_id,
            "status": status,
            **data
        }, default=str)
    )


# 注册决策 WebSocket 端点
@router.websocket("/decisions")
async def websocket_decisions(
    websocket: WebSocket,
    token: str = Query(..., description="认证令牌"),
    interval: float = Query(1.0, ge=0.5, le=10.0, description="推送间隔（秒）"),
    limit: int = Query(10, ge=1, le=50, description="返回决策数量上限"),
):
    """推送决策器输出的决策列表（带避险约束过滤后的结果）"""
    await decision_websocket_endpoint(websocket, token=token, interval=interval, limit=limit)
