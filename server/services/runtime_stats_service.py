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
        
        # 获取或设置初始资金（默认1000 USDT）
        async with pool.acquire() as conn:
            # 检查是否已有初始余额记录
            existing_balance = await redis.hget(STATS_KEY, "initial_balance")
            if not existing_balance:
                # 设置默认初始资金
                initial = 1000.0
                current = 1000.0
                await redis.hset(STATS_KEY, mapping={
                    "initial_balance": str(initial),
                    "current_balance": str(current),
                    "net_profit": "0.0"
                })
                logger.info(f"✅ 设置默认初始资金: {initial} USDT")
            
            # 获取交易模式和机器人状态
            global_config = await conn.fetchrow("SELECT trading_mode, bot_status FROM global_settings LIMIT 1")
            if global_config:
                await redis.hset(STATS_KEY, mapping={
                    "trading_mode": global_config['trading_mode'] or 'paper',
                    "bot_status": global_config['bot_status'] or 'stopped'
                })
            
            # 获取启用的策略
            strategies = await conn.fetch("""
                SELECT strategy_type FROM strategy_configs WHERE is_enabled = true
            """)
            strategy_names = [s['strategy_type'] for s in strategies] if strategies else []
            await redis.hset(STATS_KEY, "active_strategies", ",".join(strategy_names) if strategy_names else "")
            logger.info(f"📊 活跃策略: {strategy_names}")
            
            # 获取启用的交易所
            exchanges = await conn.fetch("""
                SELECT DISTINCT exchange_id FROM exchange_configs WHERE is_active = true
            """)
            exchange_names = [e['exchange_id'] for e in exchanges] if exchanges else []
            await redis.hset(STATS_KEY, "active_exchanges", ",".join(exchange_names) if exchange_names else "")
            logger.info(f"📊 活跃交易所: {exchange_names}")
            
            # 获取交易对（使用与update相同的JOIN查询）
            pairs = await conn.fetch("""
                SELECT DISTINCT tp.symbol 
                FROM trading_pairs tp 
                JOIN exchange_trading_pairs etp ON tp.id = etp.trading_pair_id 
                WHERE etp.is_enabled = true 
                LIMIT 20
            """)
            pair_symbols = [p['symbol'] for p in pairs] if pairs else []
            await redis.hset(STATS_KEY, "trading_pairs", ",".join(pair_symbols) if pair_symbols else "")
            logger.info(f"📊 活跃交易对: {pair_symbols}")
        
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
        
        # 从Redis获取当前余额（模拟模式下不会实际变化）
        initial_str = await redis.hget(STATS_KEY, "initial_balance")
        current_str = await redis.hget(STATS_KEY, "current_balance")
        
        initial_balance = float(initial_str.decode() if isinstance(initial_str, bytes) else initial_str or "1000")
        current_balance = float(current_str.decode() if isinstance(current_str, bytes) else current_str or "1000")
        
        # 更新最后更新时间
        await redis.hset(STATS_KEY, mapping={
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
        
        # 定期从数据库刷新配置信息
        async with pool.acquire() as conn:
            # 刷新交易模式和bot状态
            global_config = await conn.fetchrow("SELECT trading_mode, bot_status FROM global_settings LIMIT 1")
            if global_config:
                await redis.hset(STATS_KEY, mapping={
                    "trading_mode": global_config['trading_mode'] or 'paper',
                    "bot_status": global_config['bot_status'] or 'running'
                })
            
            # 刷新启用的策略
            strategies = await conn.fetch("SELECT strategy_type FROM strategy_configs WHERE is_enabled = true")
            strategy_names = [s['strategy_type'] for s in strategies] if strategies else []
            await redis.hset(STATS_KEY, "active_strategies", ",".join(strategy_names) if strategy_names else "")
            
            # 刷新启用的交易所
            exchanges = await conn.fetch("SELECT DISTINCT exchange_id FROM exchange_configs WHERE is_active = true")
            exchange_names = [e['exchange_id'] for e in exchanges] if exchanges else []
            await redis.hset(STATS_KEY, "active_exchanges", ",".join(exchange_names) if exchange_names else "")
            
            # 刷新交易对
            pairs = await conn.fetch("""
                SELECT DISTINCT tp.symbol 
                FROM trading_pairs tp 
                JOIN exchange_trading_pairs etp ON tp.id = etp.trading_pair_id 
                WHERE etp.is_enabled = true 
                LIMIT 20
            """)
            pair_symbols = [p['symbol'] for p in pairs] if pairs else []
            await redis.hset(STATS_KEY, "trading_pairs", ",".join(pair_symbols) if pair_symbols else "")
    
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
        
        # 辅助函数：安全解码字节或返回字符串
        def decode_value(val, default=""):
            if val is None:
                return default
            if isinstance(val, bytes):
                return val.decode()
            return str(val)
        
        trading_mode = decode_value(stats.get("trading_mode"), "paper")
        bot_status = decode_value(stats.get("bot_status"), "running")
        
        strategies_str = decode_value(stats.get("active_strategies"), "")
        active_strategies = strategies_str.split(",") if strategies_str else ["无"]
        active_strategies = [s for s in active_strategies if s] or ["无"]
        
        exchanges_str = decode_value(stats.get("active_exchanges"), "")
        active_exchanges = exchanges_str.split(",") if exchanges_str else ["无"]
        active_exchanges = [e for e in active_exchanges if e] or ["无"]
        
        pairs_str = decode_value(stats.get("trading_pairs"), "")
        trading_pairs = pairs_str.split(",")[:10] if pairs_str else ["无"]
        trading_pairs = [p for p in trading_pairs if p] or ["无"]
        
        return {
            "current_time": datetime.now().isoformat(),
            "runtime": {
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "total_seconds": runtime_seconds
            },
            "trading_mode": trading_mode,
            "bot_status": bot_status,
            "active_strategies": active_strategies,
            "active_exchanges": active_exchanges,
            "trading_pairs": trading_pairs,
            "initial_balance": float(decode_value(stats.get("initial_balance"), "1000")),
            "current_balance": float(decode_value(stats.get("current_balance"), "1000")),
            "net_profit": float(decode_value(stats.get("net_profit"), "0")),
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
