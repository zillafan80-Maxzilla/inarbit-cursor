"""
运行时统计 API 路由
提供实时统计信息和交易日志
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, List
import logging

from ..services.runtime_stats_service import get_runtime_stats_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/stats", tags=["Runtime Statistics"])


@router.get("/realtime")
async def get_realtime_stats() -> Dict:
    """
    获取实时统计信息
    
    返回：
    - 当前时间
    - 运行时长
    - 交易模式、策略、交易所、币对
    - 资金、收益信息
    - 收益曲线数据
    """
    try:
        service = await get_runtime_stats_service()
        stats = await service.get_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/recent")
async def get_recent_trades(limit: int = 50) -> Dict:
    """
    获取最近的交易记录
    
    参数：
    - limit: 返回记录数，默认50，最多100
    """
    try:
        if limit > 100:
            limit = 100
        
        service = await get_runtime_stats_service()
        trades = await service.get_recent_trades(limit)
        return {"success": True, "data": trades, "count": len(trades)}
    except Exception as e:
        logger.error(f"获取交易记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade/log")
async def log_trade(trade_data: Dict) -> Dict:
    """
    记录交易日志
    
    请求体：
    {
        "type": "buy/sell",
        "symbol": "BTC/USDT",
        "side": "buy/sell",
        "price": 50000,
        "amount": 0.1,
        "profit": 10.5
    }
    """
    try:
        service = await get_runtime_stats_service()
        await service.log_trade(trade_data)
        return {"success": True, "message": "交易已记录"}
    except Exception as e:
        logger.error(f"记录交易失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
