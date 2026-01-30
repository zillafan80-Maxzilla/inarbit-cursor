"""
套利引擎核心
实现各种套利策略的核心算法
"""
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

from ..db import get_pg_pool, get_redis
from ..services.config_service import get_config_service

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """套利机会"""
    strategy_type: str
    path: str  # 套利路径描述
    expected_profit_rate: float
    expected_profit_amount: float
    exchanges: List[str]
    symbols: List[str]
    timestamp: datetime
    
    def to_dict(self) -> dict:
        return {
            'strategyType': self.strategy_type,
            'path': self.path,
            'profitRate': self.expected_profit_rate,
            'profitAmount': self.expected_profit_amount,
            'exchanges': self.exchanges,
            'symbols': self.symbols,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class PriceData:
    """价格数据"""
    symbol: str
    exchange_id: str
    bid: float  # 买一价
    ask: float  # 卖一价
    timestamp: datetime


class ArbitrageEngine:
    """
    套利引擎
    扫描并发现套利机会
    """
    
    def __init__(self):
        self._config_service = None
        self._price_cache: Dict[str, PriceData] = {}  # symbol@exchange -> PriceData
        self._opportunities: List[ArbitrageOpportunity] = []
    
    async def initialize(self):
        """初始化套利引擎"""
        self._config_service = await get_config_service()
        logger.info("套利引擎初始化完成")
    
    # ============================================
    # 三角套利算法
    # ============================================
    
    async def scan_triangular(
        self,
        exchange_id: str,
        base_currency: str = 'USDT',
        min_profit_rate: float = 0.001
    ) -> List[ArbitrageOpportunity]:
        """
        扫描三角套利机会
        例如: USDT -> BTC -> ETH -> USDT
        """
        opportunities = []
        
        try:
            # 获取该交易所支持的交易对
            pairs = await self._config_service.get_pairs_for_exchange(exchange_id)
            
            # 构建交易对图
            # 找出所有以base_currency开头或结尾的交易对
            quote_pairs = [p for p in pairs if p.quote == base_currency]
            
            for pair_a in quote_pairs:
                # pair_a: X/USDT
                currency_a = pair_a.base  # X
                
                for pair_b in pairs:
                    if pair_b.base != currency_a:
                        continue
                    # pair_b: X/Y
                    currency_b = pair_b.quote  # Y
                    
                    # 查找 Y/USDT
                    pair_c = next((p for p in quote_pairs if p.base == currency_b), None)
                    if not pair_c:
                        continue
                    
                    # 计算三角套利收益
                    profit_rate = await self._calculate_triangular_profit(
                        exchange_id,
                        pair_a.symbol,  # USDT -> X
                        pair_b.symbol,  # X -> Y
                        pair_c.symbol   # Y -> USDT
                    )
                    
                    if profit_rate > min_profit_rate:
                        path = f"{base_currency} → {currency_a} → {currency_b} → {base_currency}"
                        opportunities.append(ArbitrageOpportunity(
                            strategy_type='triangular',
                            path=path,
                            expected_profit_rate=profit_rate,
                            expected_profit_amount=profit_rate * 1000,  # 假设1000 USDT本金
                            exchanges=[exchange_id],
                            symbols=[pair_a.symbol, pair_b.symbol, pair_c.symbol],
                            timestamp=datetime.now()
                        ))
            
        except Exception as e:
            logger.error(f"三角套利扫描失败: {e}")
        
        return opportunities
    
    async def _calculate_triangular_profit(
        self,
        exchange_id: str,
        symbol_a: str,
        symbol_b: str,
        symbol_c: str
    ) -> float:
        """计算三角套利收益率"""
        try:
            # 获取价格（从缓存或模拟）
            price_a = await self._get_price(exchange_id, symbol_a)
            price_b = await self._get_price(exchange_id, symbol_b)
            price_c = await self._get_price(exchange_id, symbol_c)
            
            if not all([price_a, price_b, price_c]):
                return 0.0
            
            # 计算套利路径
            # Step 1: USDT -> X (买入X，用ask价)
            amount_x = 1000 / price_a.ask
            
            # Step 2: X -> Y (卖出X换Y，用bid价)
            amount_y = amount_x * price_b.bid
            
            # Step 3: Y -> USDT (卖出Y换USDT，用bid价)
            final_usdt = amount_y * price_c.bid
            
            # 扣除手续费（假设0.1%）
            fee_rate = 0.001
            final_usdt *= (1 - fee_rate) ** 3
            
            profit_rate = (final_usdt - 1000) / 1000
            return profit_rate
            
        except Exception as e:
            logger.error(f"计算三角套利收益失败: {e}")
            return 0.0
    
    # ============================================
    # 跨交易所套利算法
    # ============================================
    
    async def scan_cross_exchange(
        self,
        symbol: str,
        min_profit_rate: float = 0.002
    ) -> List[ArbitrageOpportunity]:
        """
        扫描跨交易所套利机会
        在低价交易所买入，高价交易所卖出
        """
        opportunities = []
        
        try:
            # 获取所有已连接的交易所
            exchanges = await self._config_service.get_connected_exchanges()
            
            # 收集各交易所价格
            prices = []
            for ex in exchanges:
                price = await self._get_price(ex.id, symbol)
                if price:
                    prices.append(price)
            
            if len(prices) < 2:
                return opportunities
            
            # 计算最大价差
            for i, buy_price in enumerate(prices):
                for j, sell_price in enumerate(prices):
                    if i == j:
                        continue
                    
                    # 在i交易所买入（用ask），在j交易所卖出（用bid）
                    profit_rate = (sell_price.bid - buy_price.ask) / buy_price.ask
                    
                    # 扣除手续费
                    profit_rate -= 0.002  # 两次交易手续费
                    
                    if profit_rate > min_profit_rate:
                        path = f"{buy_price.exchange_id} → {sell_price.exchange_id}"
                        opportunities.append(ArbitrageOpportunity(
                            strategy_type='cross_exchange',
                            path=path,
                            expected_profit_rate=profit_rate,
                            expected_profit_amount=profit_rate * 1000,
                            exchanges=[buy_price.exchange_id, sell_price.exchange_id],
                            symbols=[symbol],
                            timestamp=datetime.now()
                        ))
            
        except Exception as e:
            logger.error(f"跨交易所套利扫描失败: {e}")
        
        return opportunities
    
    # ============================================
    # 价格获取（模拟/实际）
    # ============================================
    
    async def _get_price(self, exchange_id: str, symbol: str) -> Optional[PriceData]:
        """获取价格数据"""
        cache_key = f"{symbol}@{exchange_id}"
        
        # 检查缓存
        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            # 检查是否过期（5秒）
            if (datetime.now() - cached.timestamp).total_seconds() < 5:
                return cached
        
        # 从Redis获取实时价格
        try:
            redis = await get_redis()
            price_data = await redis.hgetall(f"price:{symbol}:{exchange_id}")
            
            if price_data:
                price = PriceData(
                    symbol=symbol,
                    exchange_id=exchange_id,
                    bid=float(price_data.get('bid', 0)),
                    ask=float(price_data.get('ask', 0)),
                    timestamp=datetime.now()
                )
                self._price_cache[cache_key] = price
                return price
        except Exception as e:
            logger.debug(f"从Redis获取价格失败: {e}")
        
        # 返回模拟价格（测试用）
        return self._generate_mock_price(exchange_id, symbol)
    
    def _generate_mock_price(self, exchange_id: str, symbol: str) -> PriceData:
        """生成模拟价格（测试用）"""
        import random
        
        base_prices = {
            'BTC/USDT': 68000,
            'ETH/USDT': 3500,
            'BNB/USDT': 380,
            'SOL/USDT': 140,
            'XRP/USDT': 0.6,
            'DOGE/USDT': 0.12,
        }
        
        base = base_prices.get(symbol, 100)
        spread = base * 0.001  # 0.1% 点差
        variation = base * 0.0001 * random.uniform(-1, 1)  # 微小随机变化
        
        return PriceData(
            symbol=symbol,
            exchange_id=exchange_id,
            bid=base - spread / 2 + variation,
            ask=base + spread / 2 + variation,
            timestamp=datetime.now()
        )
    
    # ============================================
    # 机会管理
    # ============================================
    
    def get_opportunities(self, limit: int = 10) -> List[Dict]:
        """获取最新套利机会"""
        sorted_opps = sorted(
            self._opportunities,
            key=lambda x: x.expected_profit_rate,
            reverse=True
        )
        return [opp.to_dict() for opp in sorted_opps[:limit]]
    
    async def scan_all(self) -> int:
        """扫描所有套利机会"""
        self._opportunities.clear()
        
        # 获取已连接的交易所
        exchanges = await self._config_service.get_connected_exchanges()
        
        # 三角套利扫描
        for ex in exchanges:
            opps = await self.scan_triangular(ex.id)
            self._opportunities.extend(opps)
        
        # 跨交易所套利扫描
        pairs = await self._config_service.get_all_pairs()
        for pair in pairs[:5]:  # 限制扫描前5个交易对
            opps = await self.scan_cross_exchange(pair.symbol)
            self._opportunities.extend(opps)
        
        logger.info(f"扫描完成，发现 {len(self._opportunities)} 个套利机会")
        return len(self._opportunities)


# ============================================
# 便捷函数
# ============================================

_arbitrage_engine: Optional[ArbitrageEngine] = None

async def get_arbitrage_engine() -> ArbitrageEngine:
    """获取套利引擎实例"""
    global _arbitrage_engine
    if _arbitrage_engine is None:
        _arbitrage_engine = ArbitrageEngine()
        await _arbitrage_engine.initialize()
    return _arbitrage_engine
