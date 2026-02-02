"""
运行时统计服务 - 使用Redis存储实时统计数据
跟踪系统运行时间、资金、收益等信息
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal

from ..db import get_redis, get_pg_pool

logger = logging.getLogger(__name__)

STATS_KEY = "runtime:stats"
PROFIT_HISTORY_KEY = "runtime:profit_history"
TRADE_LOG_KEY = "runtime:trade_log"


class RuntimeStatsService:
    """运行时统计服务"""
    
    def __init__(self):
        self._start_time: Optional[float] = None
        self._update_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
    
    async def initialize(self):
        """初始化统计信息"""
        redis = await get_redis()
        pool = await get_pg_pool()
        
        # 检查是否已有运行时间记录，如果没有则初始化
        existing_start = await redis.hget(STATS_KEY, "start_timestamp")
        if not existing_start:
            self._start_time = time.time()
            await redis.hset(STATS_KEY, "start_timestamp", str(self._start_time))
            logger.info(f"✅ 初始化运行统计，开始时间: {datetime.fromtimestamp(self._start_time)}")
        else:
            self._start_time = float(existing_start)
            logger.info(f"✅ 恢复运行统计，开始时间: {datetime.fromtimestamp(self._start_time)}")
        
        # 获取初始资金（从paper_trading表）
        async with pool.acquire() as conn:
            paper_config = await conn.fetchrow("""
                SELECT initial_balance, current_balance 
                FROM paper_trading 
                ORDER BY created_at DESC LIMIT 1
            """)
            
            if paper_config:
                initial = float(paper_config['initial_balance'])
                current = float(paper_config['current_balance'])
                await redis.hset(STATS_KEY, mapping={
                    "initial_balance": str(initial),
                    "current_balance": str(current),
                    "net_profit": str(current - initial)
                })
            
            # 获取交易模式
            global_config = await conn.fetchrow("SELECT trading_mode FROM global_config LIMIT 1")
            if global_config:
                await redis.hset(STATS_KEY, "trading_mode", global_config['trading_mode'])
            
            # 获取启用的策略
            strategies = await conn.fetch("""
                SELECT strategy_type FROM strategy_configs WHERE is_enabled = true
            """)
            strategy_names = [s['strategy_type'] for s in strategies]
            await redis.hset(STATS_KEY, "active_strategies", ",".join(strategy_names))
            
            # 获取启用的交易所
            exchanges = await conn.fetch("""
                SELECT DISTINCT exchange_id FROM exchange_configs WHERE is_active = true
            """)
            exchange_names = [e['exchange_id'] for e in exchanges]
            await redis.hset(STATS_KEY, "active_exchanges", ",".join(exchange_names))
            
            # 获取交易对
            pairs = await conn.fetch("""
                SELECT symbol FROM trading_pairs WHERE is_active = true LIMIT 20
            """)
            pair_symbols = [p['symbol'] for p in pairs]
            await redis.hset(STATS_KEY, "trading_pairs", ",".join(pair_symbols))
        
        logger.info("✅ 运行统计信息初始化完成")
    
    async def start(self):
        """启动统计更新任务"""
        if self._update_task and not self._update_task.done():
            return
        self._stop_event.clear()
        self._update_task = asyncio.create_task(self._update_loop())
        logger.info("✅ 运行统计服务已启动")
    
    async def stop(self):
        """停止统计更新任务"""
        self._stop_event.set()
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except:
                pass
        logger.info("✅ 运行统计服务已停止")
    
    async def _update_loop(self):
        """定期更新统计信息"""
        while not self._stop_event.is_set():
            try:
                await self._update_stats()
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"统计更新失败: {e}")
                await asyncio.sleep(10)
    
    async def _update_stats(self):
        """更新统计信息"""
        redis = await get_redis()
        pool = await get_pg_pool()
        
        # 更新当前余额
        async with pool.acquire() as conn:
            paper_config = await conn.fetchrow("""
                SELECT current_balance FROM paper_trading 
                ORDER BY created_at DESC LIMIT 1
            """)
            
            if paper_config:
                current_balance = float(paper_config['current_balance'])
                initial_str = await redis.hget(STATS_KEY, "initial_balance")
                initial_balance = float(initial_str) if initial_str else current_balance
                
                await redis.hset(STATS_KEY, mapping={
                    "current_balance": str(current_balance),
                    "net_profit": str(current_balance - initial_balance),
                    "last_update": str(time.time())
                })
                
                # 记录利润历史（用于绘制曲线）
                timestamp = int(time.time())
                await redis.zadd(
                    PROFIT_HISTORY_KEY,
                    {f"{timestamp}:{current_balance}": timestamp}
                )
                
                # 只保留最近24小时的数据
                cutoff = timestamp - 86400
                await redis.zremrangebyscore(PROFIT_HISTORY_KEY, "-inf", cutoff)
    
    async def get_stats(self) -> Dict:
        """获取当前统计信息"""
        redis = await get_redis()
        
        stats = await redis.hgetall(STATS_KEY)
        if not stats:
            return {"status": "initializing"}
        
        # 计算运行时长
        start_ts = float(stats.get("start_timestamp", time.time()))
        runtime_seconds = int(time.time() - start_ts)
        hours = runtime_seconds // 3600
        minutes = (runtime_seconds % 3600) // 60
        seconds = runtime_seconds % 60
        
        # 获取利润历史
        profit_history = await redis.zrange(PROFIT_HISTORY_KEY, 0, -1, withscores=True)
        profit_data = [
            {"timestamp": int(score), "balance": float(member.decode().split(":")[1])}
            for member, score in profit_history
        ]
        
        return {
            "current_time": datetime.now().isoformat(),
            "runtime": {
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "total_seconds": runtime_seconds
            },
            "trading_mode": stats.get("trading_mode", "无").decode() if isinstance(stats.get("trading_mode"), bytes) else stats.get("trading_mode", "无"),
            "active_strategies": (stats.get("active_strategies", b"").decode() if isinstance(stats.get("active_strategies"), bytes) else stats.get("active_strategies", "")).split(",") if stats.get("active_strategies") else ["无"],
            "active_exchanges": (stats.get("active_exchanges", b"").decode() if isinstance(stats.get("active_exchanges"), bytes) else stats.get("active_exchanges", "")).split(",") if stats.get("active_exchanges") else ["无"],
            "trading_pairs": (stats.get("trading_pairs", b"").decode() if isinstance(stats.get("trading_pairs"), bytes) else stats.get("trading_pairs", "")).split(",")[:10] if stats.get("trading_pairs") else ["无"],
            "initial_balance": float(stats.get("initial_balance", b"0").decode() if isinstance(stats.get("initial_balance"), bytes) else stats.get("initial_balance", "0")),
            "current_balance": float(stats.get("current_balance", b"0").decode() if isinstance(stats.get("current_balance"), bytes) else stats.get("current_balance", "0")),
            "net_profit": float(stats.get("net_profit", b"0").decode() if isinstance(stats.get("net_profit"), bytes) else stats.get("net_profit", "0")),
            "profit_history": profit_data
        }
    
    async def log_trade(self, trade_data: Dict):
        """记录交易日志"""
        redis = await get_redis()
        timestamp = int(time.time() * 1000)
        
        # 存储交易记录（最多保留1000条）
        trade_entry = {
            "timestamp": timestamp,
            "type": trade_data.get("type", "unknown"),
            "symbol": trade_data.get("symbol", ""),
            "side": trade_data.get("side", ""),
            "price": trade_data.get("price", 0),
            "amount": trade_data.get("amount", 0),
            "profit": trade_data.get("profit", 0)
        }
        
        await redis.zadd(TRADE_LOG_KEY, {str(trade_entry): timestamp})
        await redis.zremrangebyrank(TRADE_LOG_KEY, 0, -1001)  # 只保留最新1000条
    
    async def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        """获取最近的交易记录"""
        redis = await get_redis()
        trades = await redis.zrevrange(TRADE_LOG_KEY, 0, limit - 1)
        
        result = []
        for trade_str in trades:
            try:
                import json
                trade_data = json.loads(trade_str.decode() if isinstance(trade_str, bytes) else trade_str)
                result.append(trade_data)
            except:
                pass
        
        return result


# 全局单例
_runtime_stats_service: Optional[RuntimeStatsService] = None


async def get_runtime_stats_service() -> RuntimeStatsService:
    """获取运行统计服务实例"""
    global _runtime_stats_service
    if _runtime_stats_service is None:
        _runtime_stats_service = RuntimeStatsService()
        await _runtime_stats_service.initialize()
    return _runtime_stats_service
