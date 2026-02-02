"""
机器人控制 API 路由
提供启动/停止机器人、策略管理、持仓查询等接口
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional
from pydantic import BaseModel
import logging

from ..db import get_pg_pool, get_redis
from ..auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bot", tags=["Bot Control"])


class BotStatusUpdate(BaseModel):
    status: str  # 'running' or 'stopped'


class StrategyToggle(BaseModel):
    is_enabled: bool


class ManualOrderRequest(BaseModel):
    symbol: str
    side: str  # 'buy' or 'sell'
    amount: float
    price: Optional[float] = None  # None for market order
    order_type: str = 'market'  # 'market' or 'limit'


# ========== 机器人控制 ==========

@router.get("/status")
async def get_bot_status(current_user = Depends(get_current_user)) -> Dict:
    """获取机器人当前状态"""
    pool = await get_pg_pool()
    redis = await get_redis()
    
    async with pool.acquire() as conn:
        global_settings = await conn.fetchrow("""
            SELECT trading_mode, bot_status, max_leverage 
            FROM global_settings LIMIT 1
        """)
        
        # 获取策略数量
        strategy_count = await conn.fetchval("""
            SELECT COUNT(*) FROM strategy_configs WHERE is_enabled = true
        """)
        
        # 从Redis获取运行时间
        start_ts = await redis.hget("runtime:stats", "start_timestamp")
        
    return {
        "success": True,
        "data": {
            "status": global_settings['bot_status'] if global_settings else 'stopped',
            "trading_mode": global_settings['trading_mode'] if global_settings else 'paper',
            "max_leverage": global_settings['max_leverage'] if global_settings else 4,
            "active_strategies": strategy_count,
            "start_timestamp": float(start_ts) if start_ts else None
        }
    }


@router.post("/start")
async def start_bot(current_user = Depends(get_current_user)) -> Dict:
    """启动机器人"""
    pool = await get_pg_pool()
    redis = await get_redis()
    
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE global_settings SET bot_status = 'running', updated_at = NOW()
        """)
        
    # 更新Redis状态
    await redis.hset("runtime:stats", "bot_status", "running")
    
    logger.info(f"🤖 机器人已启动 (by {current_user.username})")
    
    return {
        "success": True,
        "message": "机器人已启动",
        "status": "running"
    }


@router.post("/stop")
async def stop_bot(current_user = Depends(get_current_user)) -> Dict:
    """停止机器人"""
    pool = await get_pg_pool()
    redis = await get_redis()
    
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE global_settings SET bot_status = 'stopped', updated_at = NOW()
        """)
        
    # 更新Redis状态
    await redis.hset("runtime:stats", "bot_status", "stopped")
    
    logger.info(f"🛑 机器人已停止 (by {current_user.username})")
    
    return {
        "success": True,
        "message": "机器人已停止",
        "status": "stopped"
    }


@router.post("/restart")
async def restart_bot(current_user = Depends(get_current_user)) -> Dict:
    """重启机器人"""
    await stop_bot(current_user)
    await start_bot(current_user)
    
    logger.info(f"🔄 机器人已重启 (by {current_user.username})")
    
    return {
        "success": True,
        "message": "机器人已重启",
        "status": "running"
    }


# ========== 策略管理 ==========

@router.get("/strategies")
async def list_strategies(current_user = Depends(get_current_user)) -> Dict:
    """获取所有策略配置"""
    pool = await get_pg_pool()
    
    async with pool.acquire() as conn:
        strategies = await conn.fetch("""
            SELECT id, strategy_type, name, description, is_enabled, priority, config, created_at
            FROM strategy_configs 
            ORDER BY priority
        """)
        
    return {
        "success": True,
        "data": [dict(s) for s in strategies],
        "count": len(strategies)
    }


@router.post("/strategy/{strategy_id}/toggle")
async def toggle_strategy(
    strategy_id: str, 
    toggle: StrategyToggle,
    current_user = Depends(get_current_user)
) -> Dict:
    """启用/禁用策略"""
    pool = await get_pg_pool()
    
    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE strategy_configs 
            SET is_enabled = $1, updated_at = NOW()
            WHERE id = $2
        """, toggle.is_enabled, strategy_id)
        
        strategy = await conn.fetchrow("""
            SELECT strategy_type, name FROM strategy_configs WHERE id = $1
        """, strategy_id)
    
    if strategy:
        action = "启用" if toggle.is_enabled else "禁用"
        logger.info(f"📊 策略 {strategy['name']} 已{action} (by {current_user.username})")
        
    return {
        "success": True,
        "message": f"策略已{'启用' if toggle.is_enabled else '禁用'}",
        "strategy_id": strategy_id,
        "is_enabled": toggle.is_enabled
    }


@router.put("/strategy/{strategy_id}/config")
async def update_strategy_config(
    strategy_id: str,
    config: Dict,
    current_user = Depends(get_current_user)
) -> Dict:
    """更新策略配置"""
    pool = await get_pg_pool()
    
    async with pool.acquire() as conn:
        import json
        await conn.execute("""
            UPDATE strategy_configs 
            SET config = $1::jsonb, updated_at = NOW()
            WHERE id = $2
        """, json.dumps(config), strategy_id)
        
    logger.info(f"📊 策略配置已更新: {strategy_id} (by {current_user.username})")
    
    return {
        "success": True,
        "message": "策略配置已更新",
        "strategy_id": strategy_id
    }


# ========== 持仓查询 ==========

@router.get("/positions")
async def get_positions(current_user = Depends(get_current_user)) -> Dict:
    """获取当前持仓"""
    pool = await get_pg_pool()
    redis = await get_redis()
    
    positions = []
    
    # 获取模拟盘持仓
    async with pool.acquire() as conn:
        paper_positions = await conn.fetch("""
            SELECT * FROM paper_positions WHERE user_id = $1
        """, current_user.id)
        
        for p in paper_positions:
            positions.append({
                "type": "paper",
                **dict(p)
            })
    
    # 获取做空策略持仓（从Redis）
    short_positions = await redis.hgetall("short:positions")
    if short_positions:
        for symbol, pos_str in short_positions.items():
            try:
                import json
                symbol_str = symbol.decode() if isinstance(symbol, bytes) else symbol
                pos_data = json.loads(pos_str.decode() if isinstance(pos_str, bytes) else pos_str)
                positions.append({
                    "type": "short_leverage",
                    "symbol": symbol_str,
                    **pos_data
                })
            except:
                pass
    
    return {
        "success": True,
        "data": positions,
        "count": len(positions)
    }


# ========== 手动下单 ==========

@router.post("/order/manual")
async def create_manual_order(
    order: ManualOrderRequest,
    current_user = Depends(get_current_user)
) -> Dict:
    """手动创建订单（仅模拟盘）"""
    pool = await get_pg_pool()
    
    # 检查是否为模拟盘模式
    async with pool.acquire() as conn:
        global_settings = await conn.fetchrow("""
            SELECT trading_mode FROM global_settings LIMIT 1
        """)
        
        if global_settings['trading_mode'] != 'paper':
            raise HTTPException(status_code=400, detail="手动下单仅支持模拟盘模式")
        
        # 记录订单
        order_id = await conn.fetchval("""
            INSERT INTO order_history (
                user_id, exchange_id, symbol, side, order_type, amount, price, status
            ) VALUES ($1, 'okx', $2, $3, $4, $5, $6, 'filled')
            RETURNING id
        """, current_user.id, order.symbol, order.side, order.order_type, 
            order.amount, order.price)
    
    logger.info(f"📝 手动订单已创建: {order.symbol} {order.side} {order.amount} (by {current_user.username})")
    
    return {
        "success": True,
        "message": "订单已创建",
        "order_id": str(order_id),
        "order": {
            "symbol": order.symbol,
            "side": order.side,
            "amount": order.amount,
            "price": order.price,
            "type": order.order_type
        }
    }


# ========== 收益报表 ==========

@router.get("/pnl/daily")
async def get_daily_pnl(
    days: int = 7,
    current_user = Depends(get_current_user)
) -> Dict:
    """获取每日收益报表"""
    pool = await get_pg_pool()
    
    async with pool.acquire() as conn:
        # 获取每日收益
        daily_pnl = await conn.fetch("""
            SELECT 
                DATE(created_at) as date,
                SUM(profit) as total_profit,
                COUNT(*) as trade_count
            FROM order_history
            WHERE user_id = $1 
              AND created_at >= CURRENT_DATE - $2
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """, current_user.id, days)
        
    return {
        "success": True,
        "data": [dict(d) for d in daily_pnl],
        "days": days
    }


@router.get("/pnl/summary")
async def get_pnl_summary(current_user = Depends(get_current_user)) -> Dict:
    """获取收益汇总"""
    redis = await get_redis()
    
    # 从Redis获取实时数据
    stats = await redis.hgetall("runtime:stats")
    
    def decode_val(v, default=0):
        if v is None:
            return default
        if isinstance(v, bytes):
            v = v.decode()
        try:
            return float(v)
        except:
            return default
    
    initial = decode_val(stats.get(b'initial_balance', stats.get('initial_balance')), 1000)
    current = decode_val(stats.get(b'current_balance', stats.get('current_balance')), 1000)
    net_profit = current - initial
    profit_rate = (net_profit / initial * 100) if initial > 0 else 0
    
    return {
        "success": True,
        "data": {
            "initial_balance": initial,
            "current_balance": current,
            "net_profit": net_profit,
            "profit_rate": profit_rate,
            "currency": "USDT"
        }
    }
