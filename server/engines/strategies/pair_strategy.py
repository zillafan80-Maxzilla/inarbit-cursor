"""
配对交易策略实现
基于 Z-Score 的均值回归策略
"""
import asyncio
import logging
from typing import List, Dict, Optional
from decimal import Decimal
from datetime import datetime
import statistics

logger = logging.getLogger(__name__)


class PairTradingStrategy:
    """配对交易策略"""
    
    def __init__(self, exchange_client, config: dict):
        """
        初始化配对交易策略
        
        Args:
            exchange_client: 交易所客户端
            config: 策略配置
                - pair_a: 交易对A
                - pair_b: 交易对B
                - lookback_period: 回溯周期
                - entry_z_score: 入场Z-Score阈值
                - exit_z_score: 出场Z-Score阈值
        """
        self.exchange = exchange_client
        self.config = config
        
        self.pair_a = config.get('pair_a', 'BTC/USDT')
        self.pair_b = config.get('pair_b', 'ETH/USDT')
        self.lookback = config.get('lookback_period', 100)
        self.entry_z = Decimal(str(config.get('entry_z_score', 2.0)))
        self.exit_z = Decimal(str(config.get('exit_z_score', 0.5)))
        
        # 价格历史
        self.price_history_a = []
        self.price_history_b = []
        self.spread_history = []
    
    async def execute(self, trading_mode='paper') -> Dict:
        """执行配对交易策略"""
        try:
            # 获取当前价格
            ticker_a = await self.exchange.fetch_ticker(self.pair_a)
            ticker_b = await self.exchange.fetch_ticker(self.pair_b)
            
            price_a = Decimal(str(ticker_a['last']))
            price_b = Decimal(str(ticker_b['last']))
            
            # 计算价差
            spread = price_a / price_b
            
            # 更新历史
            self.price_history_a.append(float(price_a))
            self.price_history_b.append(float(price_b))
            self.spread_history.append(float(spread))
            
            # 保持历史长度
            if len(self.spread_history) > self.lookback:
                self.spread_history.pop(0)
                self.price_history_a.pop(0)
                self.price_history_b.pop(0)
            
            # 需要足够的历史数据
            if len(self.spread_history) < 30:
                logger.debug("配对交易: 历史数据不足，继续积累")
                return {'success': True, 'action': 'accumulating_data'}
            
            # 计算Z-Score
            mean_spread = statistics.mean(self.spread_history)
            std_spread = statistics.stdev(self.spread_history)
            
            if std_spread == 0:
                return {'success': True, 'action': 'no_opportunity'}
            
            z_score = (float(spread) - mean_spread) / std_spread
            
            logger.info(f"📊 配对交易 {self.pair_a}/{self.pair_b} | Z-Score: {z_score:.2f}")
            
            # 交易信号
            if abs(z_score) > float(self.entry_z):
                signal = 'short_spread' if z_score > 0 else 'long_spread'
                logger.info(f"🔔 配对交易信号: {signal} (Z={z_score:.2f})")
                
                if trading_mode == 'paper':
                    return {
                        'success': True,
                        'mode': 'paper',
                        'signal': signal,
                        'z_score': z_score
                    }
            
            return {'success': True, 'action': 'monitoring'}
            
        except Exception as e:
            logger.error(f"配对交易策略执行失败: {e}")
            return {'success': False, 'error': str(e)}
