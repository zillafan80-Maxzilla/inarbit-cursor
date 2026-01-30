"""
简化版系统初始化 - 用于诊断问题
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def main():
    print("=" * 60)
    print("🔍 诊断测试")
    print("=" * 60)
    
    # 测试1：导入模块
    print("\n1. 测试导入...")
    try:
        from server.db.connection import DatabaseManager
        print("✅ DatabaseManager 导入成功")
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 测试2：连接数据库
    print("\n2. 测试数据库连接...")
    try:
        db = DatabaseManager.get_instance()
        await db.initialize()
        print("✅ 数据库连接成功")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 测试3：测试事务
    print("\n3. 测试数据库事务...")
    try:
        async with db.pg_transaction() as conn:
            result = await conn.fetchval("SELECT 1")
            print(f"✅ 事务测试成功 (结果: {result})")
    except Exception as e:
        print(f"❌ 事务测试失败: {e}")
        import traceback
        traceback.print_exc()
        await db.close()
        return
    
    # 测试4：测试用户表
    print("\n4. 测试用户表操作...")
    try:
        async with db.pg_connection() as conn:
            # 计数
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
            print(f"✅ 当前用户数: {count}")
            
            # 尝试删除（如果存在）
            await conn.execute("DELETE FROM users WHERE username = 'test_user'")
            print("✅ 删除测试完成")
    except Exception as e:
        print(f"❌ 用户表操作失败: {e}")
        import traceback
        traceback.print_exc()
    
    await db.close()
    print("\n" + "=" * 60)
    print("✅ 诊断完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
