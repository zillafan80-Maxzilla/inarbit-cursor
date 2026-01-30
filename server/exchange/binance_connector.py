"""
Binance 交易所连接器
提供统一的 API 调用接口，支持现货和合约交易
优化：WebSocket 实时行情、自动重连、请求限流
"""
import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import aiohttp
from aiohttp.resolver import ThreadedResolver
import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)

_BINANCE_API_ENDPOINTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://api4.binance.com",
    "https://api-gcp.binance.com",
]
_BINANCE_BASE_URL_CACHE: dict[str, object] = {"value": None, "ts": 0.0}


def _normalize_base_url(url: str) -> str:
    url = (url or "").strip()
    if url.endswith("/"):
        return url[:-1]
    return url


async def _probe_binance_base_url(session: aiohttp.ClientSession, base_url: str) -> bool:
    try:
        async with session.get(f"{base_url}/api/v3/ping", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


async def get_binance_base_url() -> str:
    env_url = _normalize_base_url(os.getenv("BINANCE_API_BASE_URL", ""))
    if env_url:
        return env_url

    cached = _BINANCE_BASE_URL_CACHE.get("value")
    ts = float(_BINANCE_BASE_URL_CACHE.get("ts") or 0.0)
    if cached and (time.time() - ts) < 300:
        return str(cached)

    endpoints = [
        _normalize_base_url(u)
        for u in os.getenv("BINANCE_API_ENDPOINTS", "").split(",")
        if u.strip()
    ] or _BINANCE_API_ENDPOINTS

    async with aiohttp.ClientSession() as session:
        for base_url in endpoints:
            if await _probe_binance_base_url(session, base_url):
                _BINANCE_BASE_URL_CACHE["value"] = base_url
                _BINANCE_BASE_URL_CACHE["ts"] = time.time()
                return base_url

    fallback = _BINANCE_API_ENDPOINTS[0]
    _BINANCE_BASE_URL_CACHE["value"] = fallback
    _BINANCE_BASE_URL_CACHE["ts"] = time.time()
    return fallback


def apply_binance_base_url(exchange: ccxt.Exchange, base_url: str) -> None:
    base_url = _normalize_base_url(base_url)
    if not base_url:
        return

    def _replace_domain(url: str) -> str:
        try:
            parsed = urlparse(url)
            base = urlparse(base_url)
            if not base.netloc:
                return url
            scheme = base.scheme or parsed.scheme
            return urlunparse((scheme, base.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        except Exception:
            return url

    urls = exchange.urls.get("api") if hasattr(exchange, "urls") else None
    if isinstance(urls, dict):
        new_urls = {}
        for k, v in urls.items():
            if not isinstance(v, str):
                new_urls[k] = v
                continue
            key = k.lower()
            if key.startswith("fapi") or key.startswith("dapi") or key.startswith("eapi"):
                new_urls[k] = v
                continue
            new_urls[k] = _replace_domain(v)
        exchange.urls["api"] = new_urls
    else:
        if isinstance(urls, str):
            exchange.urls["api"] = _replace_domain(urls)


class BinanceConnector:
    """
    Binance 交易所连接器
    封装 CCXT 库，提供统一的接口
    """
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """
        初始化 Binance 连接
        
        Args:
            api_key: API 密钥
            api_secret: API 密钥
            testnet: 是否使用测试网
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # 创建 CCXT 交易所实例
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,  # 启用请求限流
            'options': {
                'defaultType': 'spot',  # 默认现货
                'adjustForTimeDifference': True,  # 自动调整时间差
                # 避免调用受限的 SAPI 接口导致 404
                'fetchCurrencies': False,
                'fetchMargins': False
            }
        })
        
        if testnet:
            self.exchange.set_sandbox_mode(True)
            logger.info("✅ Binance Testnet 模式已启用")
        
        self._is_connected = False
        self._markets_loaded = False
        self._base_url: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """初始化连接，加载市场数据"""
        try:
            # 使用线程 DNS 解析，避免 aiodns 在部分环境下失败
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(resolver=ThreadedResolver())
                )
                self.exchange.session = self._session

            # 自动选择可用的 API 地址
            self._base_url = await get_binance_base_url()
            apply_binance_base_url(self.exchange, self._base_url)

            # 加载市场信息
            await self.exchange.load_markets()
            self._markets_loaded = True
            
            # 测试连接
            balance = await self.exchange.fetch_balance()
            
            self._is_connected = True
            logger.info(f"✅ Binance 连接成功 | API密钥有效")
            
            # 输出账户概况
            total_usdt = balance.get('USDT', {}).get('total', 0)
            logger.info(f"💰 账户余额: {total_usdt:.2f} USDT")
            
            return True
            
        except Exception as e:
            self._is_connected = False
            logger.error(f"❌ Binance 连接失败: {e}")
            raise
    
    async def test_connection(self) -> Dict:
        """
        测试交易所连接
        
        Returns:
            连接状态信息
        """
        try:
            # 确保连接已初始化
            if not self._is_connected:
                await self.initialize()
            # 获取服务器时间
            server_time = await self.exchange.fetch_time()
            
            # 获取账户信息
            balance = await self.exchange.fetch_balance()
            
            # 解析余额
            balances = []
            for currency, amounts in balance.items():
                if isinstance(amounts, dict) and amounts.get('total', 0) > 0:
                    balances.append({
                        'currency': currency,
                        'total': amounts['total'],
                        'free': amounts.get('free', 0),
                        'used': amounts.get('used', 0)
                    })
            
            return {
                'success': True,
                'connected': True,
                'server_time': server_time,
                'balances': balances,
                'exchange': 'binance',
                'testnet': self.testnet
            }
            
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return {
                'success': False,
                'connected': False,
                'error': str(e)
            }
    
    async def fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """
        获取单个交易对的 ticker
        
        Args:
            symbol: 交易对，如 'BTC/USDT'
        
        Returns:
            Ticker 数据
        """
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"获取 ticker 失败 ({symbol}): {e}")
            return None
    
    async def fetch_tickers(self, symbols: Optional[List[str]] = None) -> Dict:
        """
        批量获取 ticker 数据
        
        Args:
            symbols: 交易对列表，None 表示获取所有
        
        Returns:
            {symbol: ticker_data}
        """
        try:
            tickers = await self.exchange.fetch_tickers(symbols)
            return tickers
        except Exception as e:
            logger.error(f"批量获取 ticker 失败: {e}")
            return {}
    
    async def fetch_balance(self) -> Dict:
        """
        获取账户余额
        
        Returns:
            余额信息
        """
        try:
            balance = await self.exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            return {}
    
    async def fetch_order_book(self, symbol: str, limit: int = 20) -> Optional[Dict]:
        """
        获取订单簿（深度）
        
        Args:
            symbol: 交易对
            limit: 深度档位
        
        Returns:
            订单簿数据 {'bids': [], 'asks': []}
        """
        try:
            orderbook = await self.exchange.fetch_order_book(symbol, limit)
            return orderbook
        except Exception as e:
            logger.error(f"获取订单簿失败 ({symbol}): {e}")
            return None
    
    async def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        创建市价单
        
        Args:
            symbol: 交易对
            side: 'buy' 或 'sell'
            amount: 数量
            params: 额外参数
        
        Returns:
            订单信息
        """
        try:
            order = await self.exchange.create_market_order(
                symbol,
                side,
                amount,
                params or {}
            )
            logger.info(f"📝 市价单已创建: {side} {amount} {symbol}")
            return order
            
        except Exception as e:
            logger.error(f"创建市价单失败: {e}")
            return None
    
    async def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        创建限价单
        
        Args:
            symbol: 交易对
            side: 'buy' 或 'sell'
            amount: 数量
            price: 价格
            params: 额外参数
        
        Returns:
            订单信息
        """
        try:
            order = await self.exchange.create_limit_order(
                symbol,
                side,
                amount,
                price,
                params or {}
            )
            logger.info(f"📝 限价单已创建: {side} {amount} {symbol} @ {price}")
            return order
            
        except Exception as e:
            logger.error(f"创建限价单失败: {e}")
            return None
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        try:
            await self.exchange.cancel_order(order_id, symbol)
            logger.info(f"✅ 订单已取消: {order_id}")
            return True
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return False
    
    async def fetch_my_trades(self, symbol: str, limit: int = 50) -> List[Dict]:
        """获取交易历史"""
        try:
            trades = await self.exchange.fetch_my_trades(symbol, limit=limit)
            return trades
        except Exception as e:
            logger.error(f"获取交易历史失败: {e}")
            return []
    
    async def get_trading_fees(self) -> Dict:
        """
        获取交易手续费
        
        Returns:
            {'maker': 0.001, 'taker': 0.001}  # Binance VIP0
        """
        try:
            # Binance 默认手续费
            # VIP0: Maker 0.1%, Taker 0.1%
            # 如果有 BNB 抵扣，可以减少 25%
            
            # 尝试获取实际费率
            fees = await self.exchange.fetch_trading_fees()
            
            # 默认返回 Binance VIP0 费率
            return {
                'maker': 0.001,  # 0.1%
                'taker': 0.001   # 0.1%
            }
            
        except Exception as e:
            logger.warning(f"获取手续费失败，使用默认值: {e}")
            return {
                'maker': 0.001,
                'taker': 0.001
            }
    
    async def close(self):
        """关闭连接"""
        if self.exchange:
            await self.exchange.close()
            logger.info("Binance 连接已关闭")
        if self._session and not self._session.closed:
            await self._session.close()
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._is_connected
    
    def get_supported_symbols(self) -> List[str]:
        """获取支持的交易对列表"""
        if not self._markets_loaded:
            return []
        return list(self.exchange.markets.keys())
