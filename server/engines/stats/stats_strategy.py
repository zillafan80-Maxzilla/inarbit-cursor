"""
统计套利策略模块
基于 Z-Score 和协整分析实现币种对的均值回归交易策略
"""
import asyncio
import logging
import numpy as np
from collections import deque
from typing import Dict, List, Tuple, Optional
from ..base_strategy import BaseStrategy
from exchange.ccxt_exchange import CCXTExchange

logger = logging.getLogger(__name__)


class StatArbitrageStrategy(BaseStrategy):
    """
    统计套利策略
    核心逻辑:
    1. 监控选定的币种对 (如 BTC/USDT vs ETH/USDT)
    2. 计算价格比率的 Z-Score
    3. 当 Z-Score 超过阈值时开仓，回归均值时平仓
    """
    
    def __init__(self, engine, exchange: CCXTExchange):
        super().__init__(engine, "StatArbitrage")
        self.exchange = exchange
        
        # 策略参数 (使用静态配置)
        self.pairs = [
            ("BTC/USDT", "ETH/USDT"),  # 监控的币种对
        ]
        self.lookback_period = 60  # 回望周期 (分钟)
        self.z_entry_threshold = 2.0  # 开仓 Z-Score 阈值
        self.z_exit_threshold = 0.5  # 平仓 Z-Score 阈值
        self.position_size = 0.01  # 每次交易仓位大小 (BTC 单位)
        
        # 运行时状态
        self.price_history: Dict[str, deque] = {}  # 价格历史缓存
        self.positions: Dict[str, dict] = {}  # 当前持仓
        
    async def run(self):
        """策略主循环"""
        logger.info("统计套利策略已启动...")
        
        # 初始化价格历史缓存
        for pair in self.pairs:
            self.price_history[pair[0]] = deque(maxlen=self.lookback_period)
            self.price_history[pair[1]] = deque(maxlen=self.lookback_period)
        
        while self.engine.is_running:
            try:
                await self._update_prices()
                await self._check_signals()
                await asyncio.sleep(5)  # 5秒更新一次
            except Exception as e:
                logger.error(f"统计套利循环错误: {e}")
                await asyncio.sleep(10)
    
    async def _update_prices(self):
        """更新价格数据"""
        symbols = set()
        for pair in self.pairs:
            symbols.add(pair[0])
            symbols.add(pair[1])
        
        tickers = await self.exchange.fetch_tickers(list(symbols))
        
        for symbol, ticker in tickers.items():
            if symbol in self.price_history and ticker.get('last'):
                self.price_history[symbol].append(ticker['last'])
    
    async def _check_signals(self):
        """检查交易信号"""
        for pair in self.pairs:
            symbol_a, symbol_b = pair
            
            # 确保有足够的历史数据
            if len(self.price_history[symbol_a]) < 20:
                continue
            if len(self.price_history[symbol_b]) < 20:
                continue
            
            # 计算价格比率
            prices_a = np.array(self.price_history[symbol_a])
            prices_b = np.array(self.price_history[symbol_b])
            ratio = prices_a / prices_b
            
            # 计算 Z-Score
            z_score = self._calculate_zscore(ratio)
            pair_key = f"{symbol_a}:{symbol_b}"
            
            # 记录信号到日志
            logger.debug(f"币种对 {pair_key} Z-Score: {z_score:.3f}")
            
            # 交易逻辑
            await self._process_signal(pair_key, z_score, symbol_a, symbol_b)
    
    def _calculate_zscore(self, data: np.ndarray) -> float:
        """计算 Z-Score"""
        if len(data) < 2:
            return 0.0
        mean = np.mean(data)
        std = np.std(data)
        if std == 0:
            return 0.0
        return (data[-1] - mean) / std
    
    async def _process_signal(self, pair_key: str, z_score: float, 
                               symbol_a: str, symbol_b: str):
        """
        处理交易信号
        Z-Score > 阈值: 做空比率 (卖A买B)
        Z-Score < -阈值: 做多比率 (买A卖B)
        """
        current_pos = self.positions.get(pair_key)
        
        if current_pos is None:
            # 没有持仓，检查是否开仓
            if z_score > self.z_entry_threshold:
                # 比率过高，做空比率
                await self._open_position(pair_key, "short", symbol_a, symbol_b, z_score)
            elif z_score < -self.z_entry_threshold:
                # 比率过低，做多比率
                await self._open_position(pair_key, "long", symbol_a, symbol_b, z_score)
        else:
            # 已有持仓，检查是否平仓
            if current_pos['direction'] == "short" and z_score < self.z_exit_threshold:
                await self._close_position(pair_key, z_score)
            elif current_pos['direction'] == "long" and z_score > -self.z_exit_threshold:
                await self._close_position(pair_key, z_score)
    
    async def _open_position(self, pair_key: str, direction: str, 
                              symbol_a: str, symbol_b: str, z_score: float):
        """开仓 (模拟模式)"""
        self.positions[pair_key] = {
            'direction': direction,
            'entry_z': z_score,
            'symbol_a': symbol_a,
            'symbol_b': symbol_b,
            'amount': self.position_size
        }
        
        action = "做空" if direction == "short" else "做多"
        logger.info(f"统计套利开仓: {pair_key} {action}比率, Z-Score={z_score:.3f}")
        
        logger.info(
            "统计套利信号: %s %s/%s z=%.3f",
            direction,
            symbol_a,
            symbol_b,
            z_score,
        )
    
    async def _close_position(self, pair_key: str, z_score: float):
        """平仓 (模拟模式)"""
        pos = self.positions.pop(pair_key, None)
        if pos:
            pnl = abs(pos['entry_z'] - z_score) * 0.001  # 简化收益计算
            logger.info(f"统计套利平仓: {pair_key}, 入场Z={pos['entry_z']:.3f}, "
                       f"出场Z={z_score:.3f}, 预估PnL={pnl:.4%}")
            
            logger.info("统计套利平仓: %s, PnL=%.4f", pair_key, pnl)
