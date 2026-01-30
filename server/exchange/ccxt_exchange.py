import ccxt.async_support as ccxt
from .base_exchange import BaseExchange
import asyncio

class CCXTExchange(BaseExchange):
    def __init__(self, exchange_id, api_key=None, secret=None, password=None):
        super().__init__(exchange_id, api_key, secret, password)
        exchange_class = getattr(ccxt, exchange_id)
        self.client = exchange_class({
            'apiKey': api_key,
            'secret': secret,
            'password': password,
            'enableRateLimit': True,
        })

    async def fetch_tickers(self, symbols=None):
        try:
            return await self.client.fetch_tickers(symbols)
        except Exception as e:
            self.logger.error(f"抓取 Tickers 失败: {e}")
            return {}

    async def fetch_order_book(self, symbol, limit=20):
        try:
            return await self.client.fetch_order_book(symbol, limit)
        except Exception as e:
            self.logger.error(f"抓取 OrderBook 失败: {e}")
            return {'bids': [], 'asks': []}

    async def create_order(self, symbol, side, amount, price=None, type='limit'):
        try:
            if type == 'market':
                return await self.client.create_market_order(symbol, side, amount)
            else:
                return await self.client.create_limit_order(symbol, side, amount, price)
        except Exception as e:
            self.logger.error(f"下单失败: {e}")
            return None

    async def fetch_balance(self):
        try:
            return await self.client.fetch_balance()
        except Exception as e:
            self.logger.error(f"获取余额失败: {e}")
            return {}

    async def close(self):
        await self.client.close()
