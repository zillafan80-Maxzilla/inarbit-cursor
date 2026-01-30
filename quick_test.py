"""
快速测试脚本 - 验证所有组件能否正常导入和工作
"""
import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """测试所有关键模块能否导入"""
    print("=" * 60)
    print("🧪 测试模块导入")
    print("=" * 60)
    
    try:
        # 测试数据库模块
        from server.db.connection import DatabaseManager
        print("✅ 数据库模块导入成功")
        
        # 测试策略模块
        from server.engines.strategies import TriangularArbitrageStrategy, GridStrategy, PairTradingStrategy
        print("✅ 策略模块导入成功")
        
        # 测试交易所连接器
        from server.exchange.binance_connector import BinanceConnector
        print("✅ 交易所连接器导入成功")
        
        # 测试策略引擎
        from server.engines.strategy_engine import StrategyEngine
        print("✅ 策略引擎导入成功")
        
        print("\n🎉 所有模块导入测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 导入测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_database():
    """测试数据库连接"""
    print("\n" + "=" * 60)
    print("🧪 测试数据库连接")
    print("=" * 60)
    
    try:
        from server.db.connection import DatabaseManager
        
        db = DatabaseManager.get_instance()
        await db.initialize()
        
        # 测试 PostgreSQL
        async with db.pg_connection() as conn:
            result = await conn.fetchval("SELECT 1")
            print(f"✅ PostgreSQL 连接成功 (测试查询结果: {result})")
        
        # 测试 Redis
        await db.redis.ping()
        print("✅ Redis 连接成功")
        
        await db.close()
        
        print("\n🎉 数据库连接测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 数据库连接测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def quick_test():
    """快速测试"""
    print("\n" + "🚀" * 30)
    print("Inarbit 系统快速验证测试")
    print("🚀" * 30 + "\n")
    
    # 步骤1：测试导入
    if not test_imports():
        print("\n❌ 请先安装依赖: pip install -r server/requirements.txt")
        return False
    
    # 步骤2：测试数据库
    if not await test_database():
        print("\n❌ 请先启动数据库: docker-compose up -d")
        return False
    
    print("\n" + "=" * 60)
    print("✅ 所有快速测试通过！")
    print("=" * 60)
    print("\n下一步：运行完整初始化")
    print("  python test_system_init.py")
    print("\n")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(quick_test())
    sys.exit(0 if success else 1)
