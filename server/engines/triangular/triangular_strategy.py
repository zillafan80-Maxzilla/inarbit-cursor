import asyncio
import logging
from ..base_strategy import BaseStrategy
from exchange.ccxt_exchange import CCXTExchange

logger = logging.getLogger(__name__)

class TriangularStrategy(BaseStrategy):
    """
    三角套利策略。
    通过监控三个交易对 (例如 BTC/USDT, ETH/BTC, ETH/USDT) 的价格差异来寻找无风险获利机会。
    """
    def __init__(self, engine, exchange: CCXTExchange, symbol_triplets: list):
        super().__init__(engine, "TriangularArbitrage")
        self.exchange = exchange
        self.symbol_triplets = symbol_triplets  # 例如: [('BTC/USDT', 'ETH/BTC', 'ETH/USDT')]
        self.min_profit_threshold = 0.001  # 最小利润阈值 (0.1%)

    async def run(self):
        logger.info(f"三角套利策略已启动，监控 {len(self.symbol_triplets)} 个组合")
        while self.engine.is_running:
            for triplet in self.symbol_triplets:
                await self._check_arbitrage(triplet)
            await asyncio.sleep(1)  # 轮询间隔，高频交易通常会更短或使用 WebSocket

    async def _check_arbitrage(self, triplet):
        """
        检查单个三元组是否存在套利空间。
        """
        s1, s2, s3 = triplet
        tickers = await self.exchange.fetch_tickers([s1, s2, s3])
        if not all(s in tickers for s in [s1, s2, s3]):
            return

        # 简化计算逻辑 (A -> B -> C -> A)
        # 例如: USDT -> BTC (Buy) -> ETH (Buy) -> USDT (Sell)
        try:
            p1 = tickers[s1]['ask'] # Buy BTC with USDT
            p2 = tickers[s2]['ask'] # Buy ETH with BTC
            p3 = tickers[s3]['bid'] # Sell ETH for USDT
            
            if not (p1 and p2 and p3): return

            # 计算 1 USDT 最终能换回多少 USDT
            # 1. 1 / p1 = X BTC
            # 2. X / p2 = Y ETH
            # 3. Y * p3 = Z USDT
            final_amount = (1.0 / p1) / p2 * p3
            profit = final_amount - 1.0

            if profit > self.min_profit_threshold:
                await self._log_opportunity(triplet, profit)
        except Exception as e:
            logger.error(f"计算套利空间出错: {e}")

    async def _log_opportunity(self, triplet, profit):
        """记录套利机会"""
        logger.info(f"发现套利机会! 组合: {triplet}, 预计利润: {profit:.4%}")
