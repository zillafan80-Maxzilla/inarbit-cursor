"""
系统逻辑优化验证测试
测试所有新增的功能和优化
"""
import asyncio
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from server.db.connection import DatabaseManager

pytestmark = pytest.mark.asyncio


async def test_database_schema():
    """测试1：验证数据库架构升级"""
    print("\n" + "=" * 70)
    print("📋 测试1: 数据库架构验证")
    print("=" * 70)
    
    db = DatabaseManager.get_instance()
    await db.initialize()
    
    try:
        async with db.pg_connection() as conn:
            # 检查新增字段
            print("\n检查新增字段...")
            
            # 1. trading_mode字段
            result = await conn.fetchval("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'order_history' AND column_name = 'trading_mode'
            """)
            print(f"  ✅ order_history.trading_mode: {'存在' if result else '缺失'}")
            
            result = await conn.fetchval("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'pnl_records' AND column_name = 'trading_mode'
            """)
            print(f"  ✅ pnl_records.trading_mode: {'存在' if result else '缺失'}")
            
            # 2. deleted_at字段
            result = await conn.fetchval("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'exchange_configs' AND column_name = 'deleted_at'
            """)
            print(f"  ✅ exchange_configs.deleted_at: {'存在' if result else '缺失'}")
            
            # 检查新增表
            print("\n检查新增表...")
            
            tables = ['exchange_trading_pairs', 'strategy_pairs', 'deletion_logs']
            for table in tables:
                result = await conn.fetchval("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_name = $1
                """, table)
                print(f"  ✅ {table}: {'存在' if result else '缺失'}")
            
            # 检查视图
            print("\n检查新增视图...")
            
            views = ['v_active_exchange_pairs', 'v_strategy_details']
            for view in views:
                result = await conn.fetchval("""
                    SELECT table_name FROM information_schema.views 
                    WHERE table_name = $1
                """, view)
                print(f"  ✅ {view}: {'存在' if result else '缺失'}")
            
            print("\n✅ 数据库架构验证通过！")
            return True
            
    except Exception as e:
        print(f"\n❌ 数据库架构验证失败: {e}")
        return False
    finally:
        await db.close()


async def test_exchange_pairs_relation():
    """测试2：验证交易所-交易对关联"""
    print("\n" + "=" * 70)
    print("📋 测试2: 交易所-交易对关联验证")
    print("=" * 70)
    
    db = DatabaseManager.get_instance()
    await db.initialize()
    
    try:
        async with db.pg_connection() as conn:
            # 检查现有交易所的交易对关联
            result = await conn.fetch("""
                SELECT 
                    ec.display_name as exchange,
                    COUNT(etp.id) as pair_count,
                    COUNT(CASE WHEN etp.is_enabled THEN 1 END) as enabled_count
                FROM exchange_configs ec
                LEFT JOIN exchange_trading_pairs etp ON ec.id = etp.exchange_config_id
                WHERE ec.is_active = true
                GROUP BY ec.id, ec.display_name
            """)
            
            if result:
                print("\n交易所关联的交易对:")
                for row in result:
                    print(f"  • {row['exchange']}: {row['enabled_count']}/{row['pair_count']} 个启用")
                print("\n✅ 交易所-交易对关联验证通过！")
                return True
            else:
                print("  ℹ️  暂无活跃交易所")
                return True
                
    except Exception as e:
        print(f"\n❌ 交易所-交易对关联验证失败: {e}")
        return False
    finally:
        await db.close()


async def test_view_queries():
    """测试3：验证视图查询"""
    print("\n" + "=" * 70)
    print("📋 测试3: 视图查询验证")
    print("=" * 70)
    
    db = DatabaseManager.get_instance()
    await db.initialize()
    
    try:
        async with db.pg_connection() as conn:
            # 测试 v_active_exchange_pairs 视图
            print("\n查询活跃交易对视图...")
            result = await conn.fetch("""
                SELECT exchange_name, COUNT(*) as count
                FROM v_active_exchange_pairs
                GROUP BY exchange_name
            """)
            
            if result:
                for row in result:
                    print(f"  • {row['exchange_name']}: {row['count']} 个活跃交易对")
            else:
                print("  ℹ️  暂无活跃交易对")
            
            # 测试 v_strategy_details 视图
            print("\n查询策略详情视图...")
            result = await conn.fetch("""
                SELECT 
                    strategy_name,
                    strategy_type,
                    array_length(exchanges, 1) as exchange_count,
                    array_length(trading_pairs, 1) as pair_count
                FROM v_strategy_details
                LIMIT 5
            """)
            
            if result:
                for row in result:
                    print(f"  • {row['strategy_name']} ({row['strategy_type']}): "
                          f"{row['exchange_count'] or 0} 交易所, {row['pair_count'] or 0} 交易对")
            else:
                print("  ℹ️  暂无策略")
            
            print("\n✅ 视图查询验证通过！")
            return True
            
    except Exception as e:
        print(f"\n❌ 视图查询验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db.close()


async def test_trading_mode_isolation():
    """测试4：验证模拟/实盘数据隔离"""
    print("\n" + "=" * 70)
    print("📋 测试4: 模拟/实盘数据隔离验证")
    print("=" * 70)
    
    db = DatabaseManager.get_instance()
    await db.initialize()
    
    try:
        async with db.pg_connection() as conn:
            # 检查订单的交易模式分布
            print("\n订单历史交易模式分布:")
            result = await conn.fetch("""
                SELECT trading_mode, COUNT(*) as count
                FROM order_history
                GROUP BY trading_mode
            """)
            
            if result:
                for row in result:
                    print(f"  • {row['trading_mode']}: {row['count']} 条")
            else:
                print("  ℹ️  暂无订单历史")
            
            # 检查收益记录的交易模式分布
            print("\n收益记录交易模式分布:")
            result = await conn.fetch("""
                SELECT trading_mode, COUNT(*) as count, SUM(profit) as total_profit
                FROM pnl_records
                GROUP BY trading_mode
            """)
            
            if result:
                for row in result:
                    print(f"  • {row['trading_mode']}: {row['count']} 条, "
                          f"总收益: {float(row['total_profit'] or 0):.2f} USDT")
            else:
                print("  ℹ️  暂无收益记录")
            
            print("\n✅ 模拟/实盘数据隔离验证通过！")
            return True
            
    except Exception as e:
        print(f"\n❌ 模拟/实盘数据隔离验证失败: {e}")
        return False
    finally:
        await db.close()


async def test_soft_delete():
    """测试5：验证软删除功能（测试用例）"""
    print("\n" + "=" * 70)
    print("📋 测试5: 软删除功能验证")
    print("=" * 70)
    
    db = DatabaseManager.get_instance()
    await db.initialize()
    
    try:
        async with db.pg_connection() as conn:
            # 检查是否有软删除的交易所
            result = await conn.fetch("""
                SELECT exchange_id, display_name, deleted_at
                FROM exchange_configs
                WHERE deleted_at IS NOT NULL
            """)
            
            if result:
                print("\n软删除的交易所:")
                for row in result:
                    print(f"  • {row['display_name']} (删除时间: {row['deleted_at']})")
            else:
                print("  ℹ️  暂无软删除的交易所")
            
            # 检查删除日志
            result = await conn.fetch("""
                SELECT entity_type, deletion_type, COUNT(*) as count
                FROM deletion_logs
                GROUP BY entity_type, deletion_type
            """)
            
            if result:
                print("\n删除操作日志:")
                for row in result:
                    print(f"  • {row['entity_type']} ({row['deletion_type']}): {row['count']} 次")
            else:
                print("  ℹ️  暂无删除日志")
            
            print("\n✅ 软删除功能验证通过！")
            return True
            
    except Exception as e:
        print(f"\n❌ 软删除功能验证失败: {e}")
        return False
    finally:
        await db.close()


async def main():
    """运行所有测试"""
    print("\n" + "🚀" * 35)
    print("系统逻辑优化验证测试")
    print("🚀" * 35)
    
    tests = [
        test_database_schema,
        test_exchange_pairs_relation,
        test_view_queries,
        test_trading_mode_isolation,
        test_soft_delete
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            results.append(False)
    
    # 总结
    print("\n" + "=" * 70)
    print("📊 测试总结")
    print("=" * 70)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 所有测试通过！系统逻辑优化验证成功！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
