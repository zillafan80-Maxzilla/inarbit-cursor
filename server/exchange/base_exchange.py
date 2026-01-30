from abc import ABC, abstractmethod
import logging

class BaseExchange(ABC):
    def __init__(self, exchange_id, api_key=None, secret=None, password=None):
        self.exchange_id = exchange_id
        self.api_key = api_key
        self.secret = secret
        self.password = password
        self.logger = logging.getLogger(f"Exchange.{exchange_id}")

    @abstractmethod
    async def fetch_tickers(self, symbols):
        """抓取指定交易对的最新行情"""
        pass

    @abstractmethod
    async def fetch_order_book(self, symbol, limit=20):
        """抓取指定交易对的订单簿深度"""
        pass

    @abstractmethod
    async def create_order(self, symbol, side, amount, price=None, type='limit'):
        """下单接口"""
        pass

    @abstractmethod
    async def fetch_balance(self):
        """获取账户余额"""
        pass
