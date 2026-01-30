"""
Binance 交易所连接模块
使用 CCXT 库连接 Binance API
"""
import os
import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv

import ccxt.async_support as ccxt

load_dotenv()
logger = logging.getLogger(__name__)


class BinanceClient:
    """
    Binance 交易所客户端
    封装 CCXT 库进行交易操作
    """
    
    def __init__(self):
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.secret_key = os.getenv('BINANCE_SECRET_KEY')
        self._exchange: Optional[ccxt.binance] = None
        self._connected = False
    
    async def connect(self) -> bool:
        """连接到 Binance"""
        try:
            self._exchange = ccxt.binance({
                'apiKey': self.api_key,
                'secret': self.secret_key,
                'sandbox': False,  # 使用真实环境
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',  # 现货交易
                }
            })
            
            # 测试连接
            await self._exchange.load_markets()
            logger.info(f"Binance 连接成功，可用交易对: {len(self._exchange.markets)}")
            self._connected = True
            return True
            
        except Exception as e:
            logger.error(f"Binance 连接失败: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """断开连接"""
        if self._exchange:
            await self._exchange.close()
            self._connected = False
            logger.info("Binance 连接已断开")
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    # ============================================
    # 账户信息
    # ============================================
    
    async def get_balance(self) -> Dict:
        """获取账户余额"""
        if not self._exchange:
            raise RuntimeError("未连接到交易所")
        
        try:
            balance = await self._exchange.fetch_balance()
            # 过滤非零余额
            non_zero = {
                currency: {
                    'free': float(data['free']),
                    'used': float(data['used']),
                    'total': float(data['total'])
                }
                for currency, data in balance.items()
                if isinstance(data, dict) and float(data.get('total', 0)) > 0
            }
            return non_zero
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            raise
    
    async def get_total_balance_usdt(self) -> float:
        """获取账户总余额（USDT 计价）"""
        balance = await self.get_balance()
        total = 0.0
        
        for currency, amounts in balance.items():
            if currency == 'USDT':
                total += amounts['total']
            else:
                try:
                    ticker = await self._exchange.fetch_ticker(f"{currency}/USDT")
                    total += amounts['total'] * ticker['last']
                except:
                    pass  # 忽略无法转换的币种
        
        return total
    
    # ============================================
    # 行情数据
    # ============================================
    
    async def get_ticker(self, symbol: str) -> Dict:
        """获取单个交易对行情"""
        if not self._exchange:
            raise RuntimeError("未连接到交易所")
        
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            return {
                'symbol': symbol,
                'last': float(ticker['last']),
                'bid': float(ticker['bid']),
                'ask': float(ticker['ask']),
                'high': float(ticker['high']),
                'low': float(ticker['low']),
                'volume': float(ticker['quoteVolume']),
                'change': float(ticker['percentage']),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取行情失败 {symbol}: {e}")
            raise
    
    async def get_tickers(self, symbols: List[str]) -> List[Dict]:
        """批量获取行情"""
        tasks = [self.get_ticker(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]
    
    async def get_orderbook(self, symbol: str, limit: int = 5) -> Dict:
        """获取订单簿"""
        if not self._exchange:
            raise RuntimeError("未连接到交易所")
        
        try:
            orderbook = await self._exchange.fetch_order_book(symbol, limit)
            return {
                'symbol': symbol,
                'bids': orderbook['bids'][:limit],
                'asks': orderbook['asks'][:limit],
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取订单簿失败 {symbol}: {e}")
            raise
    
    # ============================================
    # 交易操作
    # ============================================
    
    async def create_market_order(self, symbol: str, side: str, amount: float) -> Dict:
        """创建市价单"""
        if not self._exchange:
            raise RuntimeError("未连接到交易所")
        
        try:
            order = await self._exchange.create_market_order(symbol, side, amount)
            logger.info(f"市价单已创建: {side} {amount} {symbol}")
            return {
                'id': order['id'],
                'symbol': symbol,
                'side': side,
                'amount': float(order['amount']),
                'filled': float(order['filled']),
                'price': float(order['average']) if order['average'] else None,
                'status': order['status'],
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"创建订单失败: {e}")
            raise
    
    async def create_limit_order(self, symbol: str, side: str, amount: float, price: float) -> Dict:
        """创建限价单"""
        if not self._exchange:
            raise RuntimeError("未连接到交易所")
        
        try:
            order = await self._exchange.create_limit_order(symbol, side, amount, price)
            logger.info(f"限价单已创建: {side} {amount} {symbol} @ {price}")
            return {
                'id': order['id'],
                'symbol': symbol,
                'side': side,
                'amount': float(order['amount']),
                'price': float(order['price']),
                'status': order['status'],
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"创建订单失败: {e}")
            raise
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        if not self._exchange:
            raise RuntimeError("未连接到交易所")
        
        try:
            await self._exchange.cancel_order(order_id, symbol)
            logger.info(f"订单已取消: {order_id}")
            return True
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return False
    
    # ============================================
    # 历史数据
    # ============================================
    
    async def get_recent_trades(self, symbol: str, limit: int = 50) -> List[Dict]:
        """获取最近成交记录"""
        if not self._exchange:
            raise RuntimeError("未连接到交易所")
        
        try:
            trades = await self._exchange.fetch_trades(symbol, limit=limit)
            return [
                {
                    'id': t['id'],
                    'symbol': symbol,
                    'side': t['side'],
                    'price': float(t['price']),
                    'amount': float(t['amount']),
                    'timestamp': t['timestamp']
                }
                for t in trades
            ]
        except Exception as e:
            logger.error(f"获取成交记录失败: {e}")
            raise
    
    async def get_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> List[Dict]:
        """获取K线数据"""
        if not self._exchange:
            raise RuntimeError("未连接到交易所")
        
        try:
            ohlcv = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return [
                {
                    'timestamp': candle[0],
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5]
                }
                for candle in ohlcv
            ]
        except Exception as e:
            logger.error(f"获取K线数据失败: {e}")
            raise


# ============================================
# 单例实例
# ============================================

_binance_client: Optional[BinanceClient] = None

async def get_binance_client() -> BinanceClient:
    """获取 Binance 客户端实例"""
    global _binance_client
    if _binance_client is None:
        _binance_client = BinanceClient()
    if not _binance_client.is_connected:
        await _binance_client.connect()
    return _binance_client


# ============================================
# 测试函数
# ============================================

async def test_connection():
    """测试 Binance 连接"""
    client = await get_binance_client()
    
    if client.is_connected:
        print("✅ Binance 连接成功!")
        
        # 获取 BTC 行情
        ticker = await client.get_ticker('BTC/USDT')
        print(f"BTC/USDT: ${ticker['last']:,.2f} ({ticker['change']:+.2f}%)")
        
        # 获取账户余额
        try:
            balance = await client.get_balance()
            print(f"账户资产: {len(balance)} 种")
            for currency, amounts in list(balance.items())[:5]:
                print(f"  {currency}: {amounts['total']:.4f}")
        except Exception as e:
            print(f"获取余额失败: {e}")
        
        await client.disconnect()
    else:
        print("❌ Binance 连接失败")


if __name__ == "__main__":
    asyncio.run(test_connection())
