"""
Inarbit 系统完整测试脚本
按照用户要求执行以下流程：
1. 一键重置系统数据
2. 创建 admin 用户（密码：admin）
3. 添加 Binance 交易所配置
4. 测试交易所连接
5. 提取真实交易数据
6. 配置并启动三角套利策略
7. 验证系统正常运行
"""
import asyncio
import sys
import os
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from server.db.connection import DatabaseManager
from server.exchange.binance_connector import BinanceConnector
from server.engines.strategies.triangular_strategy import TriangularArbitrageStrategy
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).parent / "server" / ".env"
load_dotenv(env_path)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SystemInitializer:
    """系统初始化器"""
    
    def __init__(self):
        self.db = None
        self.binance = None
        
    async def initialize(self):
        """初始化数据库连接"""
        logger.info("=" * 60)
        logger.info("🚀 Inarbit 高频交易系统 - 完整测试流程")
        logger.info("=" * 60)
        
        self.db = DatabaseManager.get_instance()
        await self.db.initialize()

    def _skip_exchange_steps(self) -> bool:
        return os.getenv("INARBIT_SKIP_EXCHANGE", "").strip() in {"1", "true", "True"}
    
    async def step1_reset_system(self):
        """步骤1：一键重置系统"""
        logger.info("\n" + "▓" * 60)
        logger.info("📋 步骤 1/7: 系统重置")
        logger.info("▓" * 60)
        
        env_confirm = os.getenv("INARBIT_INIT_CONFIRM", "").strip()
        if env_confirm == "YES":
            confirm = "YES"
            logger.info("使用环境变量确认重置: INARBIT_INIT_CONFIRM=YES")
        else:
            confirm = input("\nCONFIRM reset all data? (type 'YES' to continue): ")
        if confirm != 'YES':
            logger.warning("❌ 用户取消了重置操作")
            return False
        
        try:
            async with self.db.pg_transaction() as conn:
                # 清空所有数据表（保留表结构）
                logger.info("🗑️  正在清空数据表...")
                
                await conn.execute("DELETE FROM pnl_records")
                await conn.execute("DELETE FROM order_history")
                await conn.execute("DELETE FROM system_logs")
                await conn.execute("DELETE FROM strategy_exchanges")
                await conn.execute("DELETE FROM strategy_configs")
                await conn.execute("DELETE FROM exchange_configs")
                await conn.execute("DELETE FROM simulation_config")
                await conn.execute("DELETE FROM global_settings")
                await conn.execute("DELETE FROM users")
                
                logger.info("✅ 所有数据表已清空")
                
                # 清空Redis缓存
                logger.info("🗑️  正在清空 Redis 缓存...")
                await self.db.redis.flushdb()
                logger.info("✅ Redis 缓存已清空")
            
            logger.info("🎉 系统重置完成！")
            return True
            
        except Exception as e:
            logger.error(f"❌ 系统重置失败: {e}")
            return False
    
    async def step2_create_admin(self):
        """步骤2：创建 admin 用户"""
        logger.info("\n" + "▓" * 60)
        logger.info("📋 步骤 2/7: 创建 Admin 用户")
        logger.info("▓" * 60)
        
        try:
            async with self.db.pg_transaction() as conn:
                # 创建 admin 用户（密码：admin）
                user_id = await conn.fetchval("""
                    INSERT INTO users (username, password_hash, email)
                    VALUES ('admin', crypt('admin', gen_salt('bf')), 'admin@inarbit.local')
                    RETURNING id
                """)
                
                logger.info(f"✅ Admin 用户已创建 (ID: {user_id})")
                logger.info(f"   用户名: admin")
                logger.info(f"   密码: admin")
                
                # 创建默认模拟配置
                await conn.execute("""
                    INSERT INTO simulation_config (user_id, initial_capital, current_balance, realized_pnl)
                    VALUES ($1, 1000.00, 1000.00, 0)
                """, user_id)
                logger.info("✅ 模拟盘配置已创建 (初始资金: 1000 USDT)")
                
                # 创建默认全局设置
                await conn.execute("""
                    INSERT INTO global_settings (user_id, trading_mode, bot_status, default_strategy)
                    VALUES ($1, 'paper', 'stopped', 'triangular')
                """, user_id)
                logger.info("✅ 全局设置已创建 (模式: 模拟盘)")
                
                # 创建默认策略配置
                import json
                strategies = [
                    ('triangular', '三角套利', '同交易所内三个交易对的价格差套利', 1,
                     json.dumps({"min_profit_rate": 0.001, "max_slippage": 0.0005, "base_currencies": ["USDT", "BTC", "ETH"], "scan_interval_ms": 1000})),
                ]
                
                for strategy_type, name, description, priority, config in strategies:
                    await conn.execute("""
                        INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, config)
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    """, user_id, strategy_type, name, description, priority, config)

                
                logger.info("✅ 默认策略已创建 (三角套利)")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 创建用户失败: {e}")
            return False
    
    async def step3_add_binance(self):
        """步骤3：添加 Binance 交易所"""
        logger.info("\n" + "▓" * 60)
        logger.info("📋 步骤 3/7: 添加 Binance 交易所")
        logger.info("▓" * 60)
        
        if self._skip_exchange_steps():
            logger.warning("跳过交易所步骤: INARBIT_SKIP_EXCHANGE=1")
            return True

        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_SECRET_KEY') or os.getenv('BINANCE_API_SECRET')
        
        if not api_key or not api_secret:
            logger.error("❌ 未找到 Binance API 密钥，请检查 .env 文件")
            return False
        
        logger.info(f"📌 API Key: {api_key[:10]}...{api_key[-4:]}")
        
        try:
            async with self.db.pg_transaction() as conn:
                # 添加Binance交易所配置
                await conn.execute("""
                    INSERT INTO exchange_configs 
                        (user_id, exchange_id, display_name, api_key_encrypted, 
                         api_secret_encrypted, is_spot_enabled, is_futures_enabled, is_active)
                    SELECT id, 'binance', 'Binance', $1, $2, true, false, true
                    FROM users WHERE username = 'admin'
                """, api_key, api_secret)  # 注意：生产环境应该加密存储
                
                # 更新交易所状态
                await conn.execute("""
                    UPDATE exchange_status 
                    SET is_connected = true, last_heartbeat = NOW()
                    WHERE exchange_id = 'binance'
                """)

                # 绑定常用交易对到交易所配置（用于 OMS 执行）
                try:
                    await conn.execute("""
                        INSERT INTO exchange_trading_pairs (
                            exchange_config_id,
                            trading_pair_id,
                            is_enabled,
                            min_order_amount,
                            maker_fee,
                            taker_fee
                        )
                        SELECT ec.id, tp.id, true, 0.00001, 0.001, 0.001
                        FROM exchange_configs ec
                        JOIN trading_pairs tp
                          ON tp.symbol IN ('BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT')
                        WHERE ec.exchange_id = 'binance'
                          AND ec.user_id = (SELECT id FROM users WHERE username = 'admin')
                        ON CONFLICT (exchange_config_id, trading_pair_id) DO NOTHING
                    """)
                except Exception as e:
                    logger.warning(f"exchange_trading_pairs 绑定失败: {e}")
                
                logger.info("✅ Binance 交易所配置已添加")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 添加交易所失败: {e}")
            return False
    
    async def step4_test_connection(self):
        """步骤4：测试交易所连接"""
        logger.info("\n" + "▓" * 60)
        logger.info("📋 步骤 4/7: 测试交易所连接")
        logger.info("▓" * 60)
        
        if self._skip_exchange_steps():
            logger.warning("跳过交易所连接测试: INARBIT_SKIP_EXCHANGE=1")
            return True

        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_SECRET_KEY') or os.getenv('BINANCE_API_SECRET')
        
        try:
            # 创建 Binance 连接器
            self.binance = BinanceConnector(api_key, api_secret, testnet=False)
            await self.binance.initialize()
            
            # 测试连接
            result = await self.binance.test_connection()
            
            if result['success']:
                logger.info("✅ Binance 连接测试成功")
                logger.info(f"   服务器时间: {result['server_time']}")
                logger.info(f"   账户余额:")
                for balance in result['balances'][:5]:  # 只显示前5个
                    logger.info(f"      {balance['currency']}: {balance['total']:.8f}")
                return True
            else:
                logger.error(f"❌ 连接测试失败: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 连接测试失败: {e}")
            return False
    
    async def step5_fetch_market_data(self):
        """步骤5：提取真实交易数据"""
        logger.info("\n" + "▓" * 60)
        logger.info("📋 步骤 5/7: 提取真实交易数据")
        logger.info("▓" * 60)
        
        if self._skip_exchange_steps():
            logger.warning("跳过市场数据拉取: INARBIT_SKIP_EXCHANGE=1")
            return True

        if self.binance is None:
            logger.warning("跳过市场数据拉取: Binance 连接未初始化")
            return True

        try:
            # 获取几个主要交易对的实时价格
            symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']
            
            logger.info("📊 实时行情数据:")
            for symbol in symbols:
                ticker = await self.binance.fetch_ticker(symbol)
                if ticker:
                    logger.info(
                        f"   {symbol:12} | "
                        f"买价: ${ticker['bid']:>10,.2f} | "
                        f"卖价: ${ticker['ask']:>10,.2f} | "
                        f"24h量: {ticker.get('quoteVolume', 0):>15,.0f}"
                    )
                await asyncio.sleep(0.1)  # 避免限流
            
            logger.info("✅ 市场数据获取成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ 获取市场数据失败: {e}")
            return False
    
    async def step6_test_strategy(self):
        """步骤6：测试三角套利策略"""
        logger.info("\n" + "▓" * 60)
        logger.info("📋 步骤 6/7: 测试三角套利策略")
        logger.info("▓" * 60)
        
        if self._skip_exchange_steps():
            logger.warning("跳过策略测试: INARBIT_SKIP_EXCHANGE=1")
            return True

        if self.binance is None:
            logger.warning("跳过策略测试: Binance 连接未初始化")
            return True

        try:
            # 创建策略实例
            config = {
                'min_profit_rate': 0.001,  # 0.1% 最小利润
                'max_slippage': 0.0005,     # 0.05% 最大滑点
                'base_currencies': ['USDT', 'BTC', 'ETH'],
                'scan_interval_ms': 1000
            }
            
            strategy = TriangularArbitrageStrategy(self.binance, config)
            
            logger.info("🔍 正在扫描套利机会...")
            opportunities = await strategy.find_opportunities()
            
            if opportunities:
                logger.info(f"✅ 发现 {len(opportunities)} 个套利机会:")
                for i, opp in enumerate(opportunities[:3], 1):  # 显示前3个
                    logger.info(
                        f"   {i}. {opp['path']} | "
                        f"利润率: {float(opp['profit_rate'])*100:.3f}%"
                    )
            else:
                logger.info("ℹ️  当前市场无明显套利机会（这是正常的，需要持续监控）")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 策略测试失败: {e}")
            return False
    
    async def step7_verify(self):
        """步骤7：验证系统状态"""
        logger.info("\n" + "▓" * 60)
        logger.info("📋 步骤 7/7: 验证系统状态")
        logger.info("▓" * 60)
        
        try:
            async with self.db.pg_connection() as conn:
                # 检查用户
                user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
                logger.info(f"✅ 用户数量: {user_count}")
                
                # 检查交易所
                exchange_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM exchange_configs WHERE is_active = true"
                )
                logger.info(f"✅ 活跃交易所: {exchange_count}")
                
                # 检查策略
                strategy_count = await conn.fetchval("SELECT COUNT(*) FROM strategy_configs")
                logger.info(f"✅ 配置策略: {strategy_count}")
                
                # 检查模拟盘
                sim_config = await conn.fetchrow(
                    "SELECT initial_capital, current_balance FROM simulation_config LIMIT 1"
                )
                if sim_config:
                    logger.info(
                        f"✅ 模拟盘: 初始资金 ${float(sim_config['initial_capital']):.2f} USDT, "
                        f"当前余额 ${float(sim_config['current_balance']):.2f} USDT"
                    )
            
            logger.info("\n" + "=" * 60)
            logger.info("🎉 系统初始化完成！所有检查通过！")
            logger.info("=" * 60)
            logger.info("\n下一步操作:")
            logger.info("1. 启动后端服务: python -m server.app 或 uvicorn server.app:app --reload")
            logger.info("2. 启动前端服务: cd client && npm run dev")
            logger.info("3. 访问 http://localhost:5173 打开管理界面")
            logger.info("4. 在策略管理页面启动三角套利策略")
            logger.info("5. 在模拟盘仪表板查看实时运行状态")
            logger.info("\n⚠️  注意: 当前为模拟盘模式，不会执行真实交易")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 验证失败: {e}")
            return False
    
    async def cleanup(self):
        """清理资源"""
        if self.binance:
            await self.binance.close()
        if self.db:
            await self.db.close()
    
    async def run_all_steps(self):
        """运行所有步骤"""
        try:
            await self.initialize()
            
            # 执行所有步骤
            if not await self.step1_reset_system():
                return False
            
            if not await self.step2_create_admin():
                return False
            
            if not await self.step3_add_binance():
                return False
            
            if not await self.step4_test_connection():
                return False
            
            if not await self.step5_fetch_market_data():
                return False
            
            if not await self.step6_test_strategy():
                return False
            
            if not await self.step7_verify():
                return False
            
            return True
            
        finally:
            await self.cleanup()


async def main():
    """主函数"""
    initializer = SystemInitializer()
    success = await initializer.run_all_steps()
    
    if success:
        logger.info("\n✅ 所有测试步骤完成！系统已就绪！")
        return 0
    else:
        logger.error("\n❌ 测试过程中出现错误，请检查日志")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
