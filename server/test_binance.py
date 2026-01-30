"""
Binance 实时数据获取测试脚本
使用 ccxt 库连接 Binance 并获取账户余额和市场行情
"""
import asyncio
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

try:
    import ccxt.async_support as ccxt
except ImportError:
    print("请先安装 ccxt: pip install ccxt python-dotenv")
    exit(1)

async def test_binance_connection():
    """测试 Binance API 连接"""
    
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    if not api_key or not api_secret:
        print("❌ 错误: 未找到 API 密钥。请检查 .env 文件。")
        return
    
    print("🔗 正在连接 Binance...")
    
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot'
        }
    })
    
    try:
        # 1. 获取账户余额
        print("\n📊 获取账户余额...")
        balance = await exchange.fetch_balance()
        
        # 过滤出有余额的资产
        non_zero = {k: v for k, v in balance['total'].items() if v > 0}
        print(f"✅ 账户资产 (非零余额):")
        for asset, amount in non_zero.items():
            print(f"   {asset}: {amount}")
        
        # 2. 获取 BTC/USDT 行情
        print("\n📈 获取 BTC/USDT 实时行情...")
        ticker = await exchange.fetch_ticker('BTC/USDT')
        print(f"   最新价格: ${ticker['last']:,.2f}")
        print(f"   24h 涨跌: {ticker['percentage']:.2f}%")
        print(f"   24h 高/低: ${ticker['high']:,.2f} / ${ticker['low']:,.2f}")
        
        # 3. 获取三角套利相关交易对
        print("\n🔺 获取三角套利相关行情 (BTC/USDT, ETH/BTC, ETH/USDT)...")
        tickers = await exchange.fetch_tickers(['BTC/USDT', 'ETH/BTC', 'ETH/USDT'])
        for symbol, data in tickers.items():
            print(f"   {symbol}: ${data['last']:,.4f}" if data['last'] < 1 else f"   {symbol}: ${data['last']:,.2f}")
        
        print("\n✅ Binance API 连接测试成功!")
        
    except ccxt.AuthenticationError as e:
        print(f"❌ 认证失败: {e}")
    except ccxt.NetworkError as e:
        print(f"❌ 网络错误: {e}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_binance_connection())
