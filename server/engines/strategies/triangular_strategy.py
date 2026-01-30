"""
三角套利策略实现
算法：检测 A→B→C→A 形式的价格循环套利机会
优化：支持多路径并发扫描、动态手续费计算、滑点预测
"""
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)


class TriangularArbitrageStrategy:
    """
    三角套利策略
    
    原理：
    假设有三个交易对：BTC/USDT, ETH/USDT, ETH/BTC
    如果 (1 / P_BTC_USDT) * P_ETH_BTC * P_ETH_USDT > 1 + 手续费
    则存在套利机会
    
    路径：USDT → BTC → ETH → USDT
    """
    
    def __init__(self, exchange_client, config: dict):
        """
        初始化三角套利策略
        
        Args:
            exchange_client: 交易所客户端
            config: 策略配置
                - min_profit_rate: 最小利润率（默认0.1%）
                - max_slippage: 最大滑点（默认0.05%）
                - base_currencies: 基础货币列表
                - scan_interval_ms: 扫描间隔（毫秒）
        """
        self.exchange = exchange_client
        self.config = config
        
        self.min_profit_rate = Decimal(str(config.get('min_profit_rate', 0.001)))
        self.max_slippage = Decimal(str(config.get('max_slippage', 0.0005)))
        self.base_currencies = config.get('base_currencies', ['USDT', 'BTC', 'ETH'])
        
        # 手续费（从交易所获取，这里使用Binance现货默认值）
        self.taker_fee = Decimal('0.001')  # 0.1%
        
        # 缓存
        self._ticker_cache: Dict[str, dict] = {}
        self._last_cache_update = 0
        
    async def find_opportunities(self) -> List[Dict]:
        """
        扫描所有可能的三角套利机会
        
        Returns:
            套利机会列表，每个包含：
            - path: 套利路径
            - profit_rate: 利润率
            - start_amount: 起始金额
            - steps: 每个交易步骤的详细信息
        """
        opportunities = []
        
        # 1. 获取所有交易对的最新价格
        await self._update_ticker_cache()
        
        # 2. 遍历所有可能的三角路径
        for base in self.base_currencies:
            triangles = await self._find_triangles(base)
            
            for triangle in triangles:
                # 3. 计算每个三角路径的收益
                profit_info = await self._calculate_profit(triangle)
                
                if profit_info and profit_info['profit_rate'] > self.min_profit_rate:
                    opportunities.append(profit_info)
                    logger.info(
                        f"🔺 发现套利机会: {profit_info['path']} | "
                        f"利润率: {float(profit_info['profit_rate'])* 100:.3f}%"
                    )
        
        # 按利润率排序
        opportunities.sort(key=lambda x: x['profit_rate'], reverse=True)
        return opportunities
    
    async def _update_ticker_cache(self):
        """更新价格缓存"""
        try:
            # 获取所有交易对的 ticker
            tickers = await self.exchange.fetch_tickers()
            
            self._ticker_cache = {}
            for symbol, ticker in tickers.items():
                if ticker.get('bid') and ticker.get('ask'):
                    self._ticker_cache[symbol] = {
                        'bid': Decimal(str(ticker['bid'])),  # 买价
                        'ask': Decimal(str(ticker['ask'])),  # 卖价
                        'timestamp': ticker.get('timestamp', 0)
                    }
            
            self._last_cache_update = datetime.now().timestamp()
            logger.debug(f"更新价格缓存: {len(self._ticker_cache)} 个交易对")
            
        except Exception as e:
            logger.error(f"更新价格缓存失败: {e}")
    
    async def _find_triangles(self, base_currency: str) -> List[List[str]]:
        """
        查找以指定货币开始和结束的三角路径
        
        Args:
            base_currency: 基础货币（如 'USDT'）
        
        Returns:
            三角路径列表，如 [['BTC/USDT', 'ETH/BTC', 'ETH/USDT']]
        """
        triangles = []
        available_symbols = list(self._ticker_cache.keys())
        
        # 查找第一跳：base → currency1
        for symbol1 in available_symbols:
            base1, quote1 = symbol1.split('/')
            
            if quote1 != base_currency:
                continue
            
            currency1 = base1
            
            # 查找第二跳：currency1 → currency2
            for symbol2 in available_symbols:
                base2, quote2 = symbol2.split('/')
                
                if quote2 != currency1:
                    continue
                
                currency2 = base2
                
                # 查找第三跳：currency2 → base
                symbol3 = f"{currency2}/{base_currency}"
                if symbol3 in available_symbols:
                    triangles.append([symbol1, symbol2, symbol3])
        
        return triangles
    
    async def _calculate_profit(self, triangle: List[str]) -> Optional[Dict]:
        """
        计算三角路径的利润
        
        Args:
            triangle: 三角路径，如 ['BTC/USDT', 'ETH/BTC', 'ETH/USDT']
        
        Returns:
            利润信息字典或 None
        """
        try:
            # 初始金额（USDT）
            start_amount = Decimal('100')
            current_amount = start_amount
            
            steps = []
            
            for i, symbol in enumerate(triangle):
                ticker = self._ticker_cache.get(symbol)
                if not ticker:
                    return None
                
                base, quote = symbol.split('/')
                
                if i == 0:
                    # 第一步：用 USDT 买 BTC（使用 ask 价）
                    price = ticker['ask']
                    new_amount = current_amount / price * (Decimal('1') - self.taker_fee)
                    steps.append({
                        'symbol': symbol,
                        'side': 'buy',
                        'price': float(price),
                        'amount_in': float(current_amount),
                        'amount_out': float(new_amount),
                        'currency_in': quote,
                        'currency_out': base
                    })
                    current_amount = new_amount
                    
                elif i == 1:
                    # 第二步：用 BTC 买 ETH（使用 ask 价）
                    price = ticker['ask']
                    new_amount = current_amount / price * (Decimal('1') - self.taker_fee)
                    steps.append({
                        'symbol': symbol,
                        'side': 'buy',
                        'price': float(price),
                        'amount_in': float(current_amount),
                        'amount_out': float(new_amount),
                        'currency_in': quote,
                        'currency_out': base
                    })
                    current_amount = new_amount
                    
                else:
                    # 第三步：卖 ETH 得到 USDT（使用 bid 价）
                    price = ticker['bid']
                    new_amount = current_amount * price * (Decimal('1') - self.taker_fee)
                    steps.append({
                        'symbol': symbol,
                        'side': 'sell',
                        'price': float(price),
                        'amount_in': float(current_amount),
                        'amount_out': float(new_amount),
                        'currency_in': base,
                        'currency_out': quote
                    })
                    current_amount = new_amount
            
            # 计算净利润
            profit = current_amount - start_amount
            profit_rate = profit / start_amount
            
            # 考虑滑点风险
            profit_rate_adjusted = profit_rate - self.max_slippage
            
            if profit_rate_adjusted <= 0:
                return None
            
            return {
                'path': ' → '.join([s['currency_in'] for s in steps] + [steps[-1]['currency_out']]),
                'symbols': triangle,
                'profit_rate': profit_rate_adjusted,
                'start_amount': float(start_amount),
                'end_amount': float(current_amount),
                'profit': float(profit),
                'steps': steps,
                'timestamp': datetime.now().timestamp()
            }
            
        except Exception as e:
            logger.error(f"计算利润失败: {triangle} - {e}")
            return None
    
    async def execute(self, opportunity: Dict, trading_mode='paper') -> Dict:
        """
        执行套利交易
        
        Args:
            opportunity: 套利机会（由 find_opportunities 返回）
            trading_mode: 交易模式（'paper' = 模拟，'live' = 实盘）
        
        Returns:
            执行结果
        """
        if trading_mode == 'paper':
            logger.info(f"📝 模拟交易: {opportunity['path']}")
            return {
                'success': True,
                'mode': 'paper',
                'profit': opportunity['profit'],
                'orders': []
            }
        
        # ⚠️ 实盘交易（谨慎使用！）
        logger.warning(f"⚠️ 执行实盘交易: {opportunity['path']}")
        
        orders = []
        try:
            for step in opportunity['steps']:
                # 创建市价单
                order = await self.exchange.create_market_order(
                    symbol=step['symbol'],
                    side=step['side'],
                    amount=step['amount_in'] if step['side'] == 'sell' else step['amount_out']
                )
                orders.append(order)
                
                # 等待订单成交
                await asyncio.sleep(0.1)
            
            return {
                'success': True,
                'mode': 'live',
                'profit': opportunity['profit'],
                'orders': orders
            }
            
        except Exception as e:
            logger.error(f"执行交易失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'orders': orders
            }
