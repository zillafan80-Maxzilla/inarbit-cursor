"""
简化版系统初始化脚本 - 无需用户交互
自动执行所有步骤
"""
import asyncio
import sys
import os
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

from server.db.connection import DatabaseManager
from dotenv import load_dotenv

load_dotenv()

async def main():
    print("=" * 70)
    print("🚀 Inarbit 系统自动初始化")
    print("=" * 70)
    
    db = DatabaseManager.get_instance()
    await db.initialize()
    
    # 步骤1：重置系统
    print("\n📋 步骤 1/4: 重置系统数据")
    try:
        async with db.pg_transaction() as conn:
            await conn.execute("DELETE FROM pnl_records")
            await conn.execute("DELETE FROM order_history")
            await conn.execute("DELETE FROM system_logs")
            await conn.execute("DELETE FROM strategy_exchanges")
            await conn.execute("DELETE FROM strategy_configs")
            await conn.execute("DELETE FROM exchange_configs")
            await conn.execute("DELETE FROM simulation_config")
            await conn.execute("DELETE FROM global_settings")
            await conn.execute("DELETE FROM users")
        await db.redis.flushdb()
        print("✅ 系统数据已清空")
    except Exception as e:
        print(f"❌ 重置失败: {e}")
        await db.close()
        return False
    
    # 步骤2：创建admin用户
    print("\n📋 步骤 2/4: 创建admin用户")
    try:
        async with db.pg_transaction() as conn:
            user_id = await conn.fetchval("""
                INSERT INTO users (username, password_hash, email)
                VALUES ('admin', crypt('admin', gen_salt('bf')), 'admin@inarbit.local')
                RETURNING id
            """)
            print(f"✅ Admin用户已创建 | 用户名: admin | 密码: admin")
            
            # 模拟盘配置
            await conn.execute("""
                INSERT INTO simulation_config (user_id, initial_capital, current_balance, realized_pnl)
                VALUES ($1, 1000.00, 1000.00, 0)
            """, user_id)
            print("✅ 模拟盘配置已创建 (初始资金: 1000 USDT)")
            
            # 全局设置
            await conn.execute("""
                INSERT INTO global_settings (user_id, trading_mode, bot_status, default_strategy)
                VALUES ($1, 'paper', 'stopped', 'triangular')
            """, user_id)
            print("✅ 全局设置已创建")
            
            # 策略配置
            config_json = json.dumps({
                "min_profit_rate": 0.001,
                "max_slippage": 0.0005,
                "base_currencies": ["USDT", "BTC", "ETH"],
                "scan_interval_ms": 1000
            })
            await conn.execute("""
                INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, config)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            """, user_id, 'triangular', '三角套利', '同交易所内三个交易对的价格差套利', 1, config_json)
            print("✅ 三角套利策略已配置")
            
    except Exception as e:
        print(f"❌ 创建用户失败: {e}")
        import traceback
        traceback.print_exc()
        await db.close()
        return False
    
    # 步骤3：配置Binance
    print("\n📋 步骤 3/4: 配置Binance交易所")
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_SECRET_KEY')
    
    if api_key and api_secret:
        try:
            async with db.pg_transaction() as conn:
                await conn.execute("""
                    INSERT INTO exchange_configs 
                        (user_id, exchange_id, display_name, api_key_encrypted, 
                         api_secret_encrypted, is_spot_enabled, is_futures_enabled, is_active)
                    SELECT id, 'binance', 'Binance', $1, $2, true, false, true
                    FROM users WHERE username = 'admin'
                """, api_key, api_secret)
                
                await conn.execute("""
                    UPDATE exchange_status 
                    SET is_connected = true, last_heartbeat = NOW()
                    WHERE exchange_id = 'binance'
                """)
            print(f"✅ Binance已配置 | API Key: {api_key[:10]}...{api_key[-4:]}")
        except Exception as e:
            print(f"⚠️  Binance配置失败: {e}")
    else:
        print("⚠️  未找到Binance API密钥，跳过")
    
    # 步骤4：验证
    print("\n📋 步骤 4/4: 验证系统状态")
    try:
        async with db.pg_connection() as conn:
            users = await conn.fetchval("SELECT COUNT(*) FROM users")
            exchanges = await conn.fetchval("SELECT COUNT(*) FROM exchange_configs WHERE is_active = true")
            strategies = await conn.fetchval("SELECT COUNT(*) FROM strategy_configs")
            
            print(f"✅ 用户: {users} | 交易所: {exchanges} | 策略: {strategies}")
    except Exception as e:
        print(f"❌ 验证失败: {e}")
    
    await db.close()
    
    print("\n" + "=" * 70)
    print("🎉 系统初始化完成！")
    print("=" * 70)
    print("\n下一步:")
    print("1. 启动后端: cd server && python -m uvicorn app:app --reload")
    print("2. 启动前端: cd client && npm run dev")
    print("3. 访问: http://localhost:5173")
    print("4. 登录: admin / admin")
    print("\n⚠️  当前为模拟盘模式，不会执行真实交易")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
