"""
做空杠杆策略服务
当市场出现大跌时，自动做空获取收益，支持最多4倍杠杆
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal

from ..db import get_redis, get_pg_pool

logger = logging.getLogger(__name__)

PRICE_HISTORY_KEY = "short:price_history"
POSITION_KEY = "short:positions"
TRADE_LOG_KEY = "short:trades"


class ShortLeverageService:
    """做空杠杆策略服务"""
    
    def __init__(self):
        self._config: Dict = {}
        self._positions: Dict[str, Dict] = {}
        self._last_prices: Dict[str, float] = {}
        self._cooldown_until: Dict[str, datetime] = {}
        self._daily_trades: int = 0
        self._daily_reset_time: datetime = datetime.now()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
    
    async def initialize(self):
        """初始化策略配置"""
        pool = await get_pg_pool()
        
        async with pool.acquire() as conn:
            config_row = await conn.fetchrow("""
                SELECT config FROM strategy_configs 
                WHERE strategy_type = 'short_leverage' AND is_enabled = true
                LIMIT 1
            """)
            
            if config_row:
                self._config = dict(config_row['config'])
                logger.info(f"📉 做空杠杆策略配置加载: leverage={self._config.get('leverage', 1)}, "
                          f"max_leverage={self._config.get('max_leverage', 4)}")
            else:
                self._config = {
                    "symbols": ["BTC/USDT", "ETH/USDT"],
                    "market_drop_threshold": -0.03,
                    "leverage": 2,
                    "max_leverage": 4,
                    "position_size_usdt": 200,
                    "stop_loss_rate": 0.03,
                    "take_profit_rate": 0.05
                }
                logger.warning("使用默认做空策略配置")
    
    async def start(self):
        """启动策略"""
        if self._task and not self._task.done():
            return
        
        await self.initialize()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("✅ 做空杠杆策略已启动")
    
    async def stop(self):
        """停止策略"""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except:
                pass
        logger.info("✅ 做空杠杆策略已停止")
    
    async def _run_loop(self):
        """主循环"""
        while not self._stop_event.is_set():
            try:
                await self._check_market_conditions()
                await self._manage_positions()
                
                # 重置每日交易计数
                if datetime.now().date() != self._daily_reset_time.date():
                    self._daily_trades = 0
                    self._daily_reset_time = datetime.now()
                
                await asyncio.sleep(10)  # 每10秒检查一次
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"做空策略循环错误: {e}")
                await asyncio.sleep(30)
    
    async def _check_market_conditions(self):
        """检查市场条件，决定是否开仓做空"""
        redis = await get_redis()
        symbols = self._config.get('symbols', ['BTC/USDT', 'ETH/USDT'])
        drop_threshold = self._config.get('market_drop_threshold', -0.03)
        max_daily_trades = self._config.get('max_daily_trades', 10)
        
        if self._daily_trades >= max_daily_trades:
            return
        
        for symbol in symbols:
            try:
                # 检查冷却期
                if symbol in self._cooldown_until:
                    if datetime.now() < self._cooldown_until[symbol]:
                        continue
                
                # 已有持仓则跳过
                if symbol in self._positions:
                    continue
                
                # 获取当前价格
                ticker_key = f"ticker:okx:{symbol.replace('/', '')}"
                ticker_data = await redis.hgetall(ticker_key)
                
                if not ticker_data:
                    continue
                
                current_price = float(ticker_data.get(b'last', ticker_data.get('last', 0)))
                if current_price <= 0:
                    continue
                
                # 计算价格变化率
                if symbol in self._last_prices:
                    last_price = self._last_prices[symbol]
                    change_rate = (current_price - last_price) / last_price
                    
                    # 检测大跌
                    if change_rate <= drop_threshold:
                        logger.info(f"📉 检测到 {symbol} 大跌 {change_rate*100:.2f}%，准备做空")
                        await self._open_short_position(symbol, current_price, change_rate)
                
                self._last_prices[symbol] = current_price
                
            except Exception as e:
                logger.error(f"检查 {symbol} 市场条件失败: {e}")
    
    async def _open_short_position(self, symbol: str, entry_price: float, trigger_change: float):
        """开空仓"""
        redis = await get_redis()
        
        leverage = self._config.get('leverage', 2)
        max_leverage = self._config.get('max_leverage', 4)
        position_size = self._config.get('position_size_usdt', 200)
        stop_loss_rate = self._config.get('stop_loss_rate', 0.03)
        take_profit_rate = self._config.get('take_profit_rate', 0.05)
        cooldown_minutes = self._config.get('cooldown_minutes', 30)
        
        # 根据跌幅动态调整杠杆
        drop_magnitude = abs(trigger_change)
        if drop_magnitude > 0.05:
            leverage = min(leverage + 1, max_leverage)
        if drop_magnitude > 0.08:
            leverage = max_leverage
        
        # 计算止损止盈价格
        stop_loss_price = entry_price * (1 + stop_loss_rate)
        take_profit_price = entry_price * (1 - take_profit_rate)
        
        # 计算仓位大小
        amount = (position_size * leverage) / entry_price
        
        position = {
            "symbol": symbol,
            "side": "short",
            "entry_price": entry_price,
            "amount": amount,
            "leverage": leverage,
            "position_value": position_size * leverage,
            "margin": position_size,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "entry_time": datetime.now().isoformat(),
            "trigger_change": trigger_change,
            "unrealized_pnl": 0
        }
        
        self._positions[symbol] = position
        self._daily_trades += 1
        self._cooldown_until[symbol] = datetime.now() + timedelta(minutes=cooldown_minutes)
        
        # 保存到Redis
        await redis.hset(POSITION_KEY, symbol, str(position))
        
        # 记录交易日志
        await self._log_trade({
            "type": "open_short",
            "symbol": symbol,
            "price": entry_price,
            "amount": amount,
            "leverage": leverage,
            "margin": position_size,
            "trigger": f"市场跌幅 {trigger_change*100:.2f}%"
        })
        
        logger.info(f"📉 开空仓 {symbol}: 价格={entry_price:.2f}, 数量={amount:.6f}, "
                   f"杠杆={leverage}x, 保证金={position_size} USDT")
    
    async def _manage_positions(self):
        """管理现有持仓"""
        redis = await get_redis()
        
        for symbol, position in list(self._positions.items()):
            try:
                # 获取当前价格
                ticker_key = f"ticker:okx:{symbol.replace('/', '')}"
                ticker_data = await redis.hgetall(ticker_key)
                
                if not ticker_data:
                    continue
                
                current_price = float(ticker_data.get(b'last', ticker_data.get('last', 0)))
                if current_price <= 0:
                    continue
                
                entry_price = position['entry_price']
                amount = position['amount']
                leverage = position['leverage']
                
                # 计算未实现盈亏 (做空: 开仓价 - 当前价)
                price_diff = entry_price - current_price
                unrealized_pnl = price_diff * amount
                pnl_rate = price_diff / entry_price
                
                position['unrealized_pnl'] = unrealized_pnl
                position['current_price'] = current_price
                position['pnl_rate'] = pnl_rate
                
                # 检查止损
                if current_price >= position['stop_loss']:
                    logger.warning(f"⚠️ {symbol} 触发止损，当前价={current_price:.2f}, 止损价={position['stop_loss']:.2f}")
                    await self._close_position(symbol, current_price, "stop_loss")
                    continue
                
                # 检查止盈
                if current_price <= position['take_profit']:
                    logger.info(f"✅ {symbol} 触发止盈，当前价={current_price:.2f}, 止盈价={position['take_profit']:.2f}")
                    await self._close_position(symbol, current_price, "take_profit")
                    continue
                
                # 移动止损（追踪止损）
                if self._config.get('trailing_stop', False):
                    trailing_rate = self._config.get('trailing_stop_rate', 0.02)
                    # 如果盈利超过追踪止损激活点
                    if pnl_rate > trailing_rate:
                        new_stop_loss = current_price * (1 + trailing_rate)
                        if new_stop_loss < position['stop_loss']:
                            position['stop_loss'] = new_stop_loss
                            logger.info(f"📊 {symbol} 更新追踪止损: {new_stop_loss:.2f}")
                
                # 更新Redis
                await redis.hset(POSITION_KEY, symbol, str(position))
                
            except Exception as e:
                logger.error(f"管理 {symbol} 持仓失败: {e}")
    
    async def _close_position(self, symbol: str, exit_price: float, reason: str):
        """平仓"""
        redis = await get_redis()
        
        if symbol not in self._positions:
            return
        
        position = self._positions[symbol]
        entry_price = position['entry_price']
        amount = position['amount']
        margin = position['margin']
        leverage = position['leverage']
        
        # 计算实现盈亏 (做空)
        price_diff = entry_price - exit_price
        realized_pnl = price_diff * amount
        
        # 扣除手续费
        taker_fee = self._config.get('taker_fee', 0.001)
        fee = (entry_price * amount + exit_price * amount) * taker_fee
        realized_pnl -= fee
        
        pnl_rate = realized_pnl / margin
        
        # 更新统计
        stats_redis = await get_redis()
        current_balance_str = await stats_redis.hget("runtime:stats", "current_balance")
        if current_balance_str:
            current_balance = float(current_balance_str.decode() if isinstance(current_balance_str, bytes) else current_balance_str)
            new_balance = current_balance + realized_pnl
            await stats_redis.hset("runtime:stats", mapping={
                "current_balance": str(new_balance),
                "net_profit": str(new_balance - 1000)  # 假设初始1000
            })
        
        # 记录交易
        await self._log_trade({
            "type": "close_short",
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "amount": amount,
            "leverage": leverage,
            "realized_pnl": realized_pnl,
            "pnl_rate": pnl_rate,
            "fee": fee,
            "reason": reason,
            "hold_time": str(datetime.now() - datetime.fromisoformat(position['entry_time']))
        })
        
        # 移除持仓
        del self._positions[symbol]
        await redis.hdel(POSITION_KEY, symbol)
        
        emoji = "✅" if realized_pnl > 0 else "❌"
        logger.info(f"{emoji} 平仓 {symbol}: 入场={entry_price:.2f}, 出场={exit_price:.2f}, "
                   f"盈亏={realized_pnl:.2f} USDT ({pnl_rate*100:.2f}%), 原因={reason}")
    
    async def _log_trade(self, trade_data: Dict):
        """记录交易日志"""
        redis = await get_redis()
        timestamp = int(time.time() * 1000)
        
        trade_entry = {
            "timestamp": timestamp,
            "datetime": datetime.now().isoformat(),
            **trade_data
        }
        
        # 存储到运行时统计的交易日志
        import json
        await redis.zadd(TRADE_LOG_KEY, {json.dumps(trade_entry): timestamp})
        await redis.zremrangebyrank(TRADE_LOG_KEY, 0, -501)  # 保留500条
        
        # 同时记录到通用交易日志
        from .runtime_stats_service import get_runtime_stats_service
        try:
            stats_service = await get_runtime_stats_service()
            await stats_service.log_trade({
                "type": trade_data.get("type", "unknown"),
                "symbol": trade_data.get("symbol", ""),
                "side": "sell" if "short" in trade_data.get("type", "") else "buy",
                "price": trade_data.get("exit_price", trade_data.get("price", 0)),
                "amount": trade_data.get("amount", 0),
                "profit": trade_data.get("realized_pnl", 0),
                "exchange": "okx"
            })
        except:
            pass
    
    async def get_positions(self) -> List[Dict]:
        """获取当前持仓"""
        return list(self._positions.values())
    
    async def get_config(self) -> Dict:
        """获取策略配置"""
        return self._config


# 全局单例
_short_leverage_service: Optional[ShortLeverageService] = None


async def get_short_leverage_service() -> ShortLeverageService:
    """获取做空杠杆服务实例"""
    global _short_leverage_service
    if _short_leverage_service is None:
        _short_leverage_service = ShortLeverageService()
        await _short_leverage_service.initialize()
    return _short_leverage_service
