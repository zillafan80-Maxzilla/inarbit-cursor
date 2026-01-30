"""
网格交易策略实现
在价格区间内布置网格，自动高抛低吸
"""
import asyncio
import logging
from typing import List, Dict, Optional
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)


class GridStrategy:
    """网格交易策略"""
    
    def __init__(self, exchange_client, config: dict):
        """
        初始化网格策略
        
        Args:
            exchange_client: 交易所客户端
            config: 策略配置
                - symbol: 交易对
                - upper_price: 网格上限价格
                - lower_price: 网格下限价格
                - grid_count: 网格数量
                - amount_per_grid: 每格交易金额
        """
        self.exchange = exchange_client
        self.config = config
        
        self.symbol = config.get('symbol', 'BTC/USDT')
        self.upper_price = Decimal(str(config.get('upper_price', 50000)))
        self.lower_price = Decimal(str(config.get('lower_price', 40000)))
        self.grid_count = int(config.get('grid_count', 10))
        self.amount_per_grid = Decimal(str(config.get('amount_per_grid', 100)))
        
        # 计算网格间距
        self.grid_step = (self.upper_price - self.lower_price) / self.grid_count
        
        # 网格订单记录
        self.grid_orders = {}
    
    async def execute(self, trading_mode='paper') -> Dict:
        """
        执行网格策略
        
        Returns:
            执行结果
        """
        try:
            # 获取当前价格
            ticker = await self.exchange.fetch_ticker(self.symbol)
            current_price = Decimal(str(ticker['last']))
            
            logger.info(f"📊 网格交易 {self.symbol} | 当前价格: ${current_price}")
            
            # 检查是否在网格范围内
            if current_price < self.lower_price or current_price > self.upper_price:
                logger.warning(f"⚠️ 价格 ${current_price} 超出网格范围 [{self.lower_price}, {self.upper_price}]")
                return {'success': False, 'reason': 'price_out_of_range'}
            
            # 计算应该挂单的位置
            buy_orders = []
            sell_orders = []
            
            for i in range(self.grid_count):
                grid_price = self.lower_price + self.grid_step * i
                
                if grid_price < current_price:
                    # 低于当前价：挂买单
                    buy_orders.append({
                        'price': float(grid_price),
                        'amount': float(self.amount_per_grid / grid_price)
                    })
                elif grid_price > current_price:
                    # 高于当前价：挂卖单
                    sell_orders.append({
                        'price': float(grid_price),
                        'amount': float(self.amount_per_grid / grid_price)
                    })
            
            if trading_mode == 'paper':
                logger.info(f"📝 模拟网格: {len(buy_orders)} 个买单, {len(sell_orders)} 个卖单")
                return {
                    'success': True,
                    'mode': 'paper',
                    'buy_orders': buy_orders,
                    'sell_orders': sell_orders
                }
            
            # 实盘模式（暂未实现完整逻辑）
            return {'success': True, 'mode': 'live'}
            
        except Exception as e:
            logger.error(f"网格策略执行失败: {e}")
            return {'success': False, 'error': str(e)}
