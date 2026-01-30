"""
交易所管理服务 - 优化版
实现完整的业务逻辑：
1. 新增交易所时自动获取交易对
2. 软删除和硬删除支持
3. 级联删除相关数据
4. 审计日志记录
"""
import asyncio
import logging
from typing import List, Dict, Optional
from uuid import UUID
from datetime import datetime
import hashlib

from ..db import get_pg_pool, get_redis
from ..exchange.binance_connector import BinanceConnector

logger = logging.getLogger(__name__)


class ExchangeService:
    """交易所管理服务"""
    
    @staticmethod
    async def setup_exchange(
        user_id: UUID,
        exchange_type: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
        display_name: Optional[str] = None
    ) -> Dict:
        """
        完整的交易所设置流程
        
        步骤：
        1. 验证API密钥
        2. 获取交易所支持的交易对
        3. 保存交易所配置
        4. 保存交易所-交易对关联
        5. 返回设置结果
        """
        logger.info(f"🔧 开始设置交易所: {exchange_type}")
        
        # 步骤1: 创建连接器并测试
        if exchange_type.lower() == 'binance':
            connector = BinanceConnector(api_key, api_secret)
        else:
            raise ValueError(f"暂不支持的交易所: {exchange_type}")
        
        try:
            await connector.initialize()
            test_result = await connector.test_connection()
            
            if not test_result['success']:
                raise Exception(f"连接失败: {test_result.get('error')}")
            
            logger.info(f"✅ API密钥验证成功")
            
        except Exception as e:
            logger.error(f"❌ API密钥验证失败: {e}")
            raise
        
        # 步骤2: 获取所有交易对
        try:
            await connector.exchange.load_markets()
            markets = connector.exchange.markets
            active_pairs = [
                symbol for symbol, market in markets.items()
                if market.get('active', False) and market.get('spot', False)
            ]
            logger.info(f"📊 获取到 {len(active_pairs)} 个活跃现货交易对")
            
        except Exception as e:
            logger.error(f"❌ 获取交易对失败: {e}")
            raise
        finally:
            await connector.close()
        
        # 步骤3: 保存到数据库
        pool = await get_pg_pool()
        
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # 3.1 保存交易所配置
                    exchange_id = await conn.fetchval("""
                        INSERT INTO exchange_configs 
                            (user_id, exchange_id, display_name, api_key_encrypted, 
                             api_secret_encrypted, passphrase_encrypted,
                             is_spot_enabled, is_futures_enabled, is_active)
                        VALUES ($1, $2, $3, $4, $5, $6, true, false, true)
                        ON CONFLICT (user_id, exchange_id) DO UPDATE
                        SET display_name = EXCLUDED.display_name,
                            api_key_encrypted = EXCLUDED.api_key_encrypted,
                            api_secret_encrypted = EXCLUDED.api_secret_encrypted,
                            passphrase_encrypted = EXCLUDED.passphrase_encrypted,
                            is_spot_enabled = EXCLUDED.is_spot_enabled,
                            is_futures_enabled = EXCLUDED.is_futures_enabled,
                            is_active = true,
                            updated_at = NOW()
                        RETURNING id
                    """, user_id, exchange_type.lower(), display_name or exchange_type.capitalize(), 
                        api_key, api_secret, passphrase or '')
                    
                    logger.info(f"✅ 交易所配置已保存: {exchange_id}")
                    
                    # 3.2 保存主流交易对（先保存到trading_pairs表如果不存在）
                    major_pairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 
                                   'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'MATIC/USDT']
                    
                    saved_count = 0
                    for symbol in active_pairs:
                        if symbol in major_pairs or saved_count < 50:  # 限制前50个
                            # 确保trading_pairs表中有此交易对
                            base, quote = symbol.split('/')
                            pair_id = await conn.fetchval("""
                                INSERT INTO trading_pairs (symbol, base_currency, quote_currency, is_active)
                                VALUES ($1, $2, $3, true)
                                ON CONFLICT (symbol) DO UPDATE SET is_active = true
                                RETURNING id
                            """, symbol, base, quote)
                            
                            # 保存交易所-交易对关联（表可能尚未迁移创建）
                            try:
                                await conn.execute("""
                                    INSERT INTO exchange_trading_pairs 
                                        (exchange_config_id, trading_pair_id, is_enabled, 
                                         min_order_amount, maker_fee, taker_fee)
                                    VALUES ($1, $2, $3, 0.00001, 0.001, 0.001)
                                    ON CONFLICT (exchange_config_id, trading_pair_id) DO NOTHING
                                """, exchange_id, pair_id, symbol in major_pairs)
                            except Exception:
                                pass
                            
                            saved_count += 1
                    
                    logger.info(f"✅ 已保存 {saved_count} 个交易对关联")
                    
                    # 3.3 更新exchange_status
                    await conn.execute("""
                        UPDATE exchange_status 
                        SET last_heartbeat = NOW()
                        WHERE exchange_id = $1
                    """, exchange_type.lower())
            
            return {
                'success': True,
                'exchange_id': str(exchange_id),
                'trading_pairs_count': saved_count,
                'major_pairs': major_pairs,
                'message': f'成功设置{display_name or exchange_type}交易所'
            }
            
        except Exception as e:
            logger.error(f"❌ 保存交易所配置失败: {e}")
            raise
    
    @staticmethod
    async def soft_delete_exchange(exchange_id: UUID, user_id: UUID) -> Dict:
        """
        软删除交易所（停用但保留历史数据）
        """
        logger.info(f"🗑️  软删除交易所: {exchange_id}")
        
        pool = await get_pg_pool()
        
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # 1. 获取统计信息
                    stats = await conn.fetchrow("""
                        SELECT 
                            ec.exchange_id as name,
                            (SELECT COUNT(*) FROM order_history oh 
                             JOIN strategy_configs sc ON sc.id = oh.strategy_id
                             WHERE oh.exchange_id = ec.exchange_id AND sc.user_id = $2) as order_count,
                            (SELECT COUNT(*) FROM pnl_records pr 
                             JOIN strategy_configs sc2 ON sc2.id = pr.strategy_id
                             WHERE pr.exchange_id = ec.exchange_id AND sc2.user_id = $2) as pnl_count,
                            (SELECT COUNT(*) FROM strategy_exchanges se
                             JOIN strategy_configs sc3 ON sc3.id = se.strategy_id
                             WHERE se.exchange_config_id = ec.id AND sc3.user_id = $2) as strategy_count
                        FROM exchange_configs ec
                        WHERE ec.id = $1 AND ec.user_id = $2
                    """, exchange_id, user_id)
                    
                    if not stats:
                        raise ValueError("交易所不存在")
                    
                    # 2. 停用交易所
                    await conn.execute("""
                        UPDATE exchange_configs 
                        SET is_active = false, deleted_at = NOW()
                        WHERE id = $1 AND user_id = $2
                    """, exchange_id, user_id)
                    
                    # 3. 禁用所有使用该交易所的策略
                    await conn.execute("""
                        UPDATE strategy_configs SET is_enabled = false
                        WHERE id IN (
                            SELECT strategy_id FROM strategy_exchanges 
                            WHERE exchange_config_id = $1
                        )
                          AND user_id = $2
                    """, exchange_id, user_id)
                    
                    # 4. 记录删除日志
                    await conn.execute("""
                        INSERT INTO deletion_logs 
                            (entity_type, entity_id, deletion_type, deleted_by, metadata)
                        VALUES ('exchange', $1, 'soft', $2, $3::jsonb)
                    """, exchange_id, user_id, {
                        'exchange_name': stats['name'],
                        'orders': stats['order_count'],
                        'pnl_records': stats['pnl_count'],
                        'strategies_affected': stats['strategy_count']
                    })
                    
                    # 5. 记录系统日志
                    await conn.execute("""
                        INSERT INTO system_logs (user_id, level, source, message, extra)
                        VALUES ($1, 'WARNING', 'exchange_service', $2, $3::jsonb)
                    """, user_id, f"交易所已软删除: {stats['name']}", {
                       'exchange_id': str(exchange_id),
                        'user_id': str(user_id)
                    })
            
            logger.info(f"✅ 交易所已软删除，历史数据已保留")
            
            return {
                'success': True,
                'deletion_type': 'soft',
                'data_retained': True,
                'stats': {
                    'orders': stats['order_count'],
                    'pnl_records': stats['pnl_count'],
                    'strategies_disabled': stats['strategy_count']
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 软删除失败: {e}")
            raise
    
    @staticmethod
    async def hard_delete_exchange(
        exchange_id: UUID, 
        user_id: UUID,
        confirm_code: str
    ) -> Dict:
        """
        硬删除交易所（永久删除所有相关数据）
        需要确认码验证
        """
        logger.warning(f"⚠️  硬删除交易所: {exchange_id}")
        
        # 验证确认码
        expected_code = hashlib.md5(f"DELETE-{exchange_id}".encode()).hexdigest()[:6].upper()
        if confirm_code.upper() != expected_code:
            raise ValueError(f"确认码错误。请输入: {expected_code}")
        
        pool = await get_pg_pool()
        redis = await get_redis()
        
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # 1. 获取要删除的数据统计
                    stats = await conn.fetchrow("""
                        SELECT 
                            ec.exchange_id as name,
                            (SELECT COUNT(*) FROM order_history oh 
                             JOIN strategy_configs sc ON sc.id = oh.strategy_id
                             WHERE oh.exchange_id = ec.exchange_id AND sc.user_id = $2) as orders,
                            (SELECT COUNT(*) FROM pnl_records pr 
                             JOIN strategy_configs sc2 ON sc2.id = pr.strategy_id
                             WHERE pr.exchange_id = ec.exchange_id AND sc2.user_id = $2) as pnl_records,
                            (SELECT COUNT(*) FROM strategy_exchanges se
                             JOIN strategy_configs sc3 ON sc3.id = se.strategy_id
                             WHERE se.exchange_config_id = ec.id AND sc3.user_id = $2) as strategies
                        FROM exchange_configs ec
                        WHERE ec.id = $1 AND ec.user_id = $2
                    """, exchange_id, user_id)
                    
                    if not stats:
                        raise ValueError("交易所不存在")
                    
                    exchange_name = stats['name']
                    
                    # 2. 按顺序级联删除
                    logger.info(f"删除策略关联...")
                    await conn.execute(
                        """
                        DELETE FROM strategy_exchanges
                        WHERE exchange_config_id = $1
                          AND EXISTS (
                            SELECT 1 FROM exchange_configs ec
                            WHERE ec.id = $1 AND ec.user_id = $2
                          )
                        """,
                        exchange_id,
                        user_id,
                    )
                    
                    logger.info(f"删除交易对关联...")
                    await conn.execute(
                        """
                        DELETE FROM exchange_trading_pairs
                        WHERE exchange_config_id = $1
                          AND EXISTS (
                            SELECT 1 FROM exchange_configs ec
                            WHERE ec.id = $1 AND ec.user_id = $2
                          )
                        """,
                        exchange_id,
                        user_id,
                    )
                    
                    logger.info(f"删除订单历史...")
                    await conn.execute(
                        """
                        DELETE FROM order_history oh
                        USING strategy_configs sc
                        WHERE oh.strategy_id = sc.id
                          AND sc.user_id = $1
                          AND oh.exchange_id = $2
                        """,
                        user_id,
                        exchange_name,
                    )
                    
                    logger.info(f"删除收益记录...")
                    await conn.execute(
                        """
                        DELETE FROM pnl_records pr
                        USING strategy_configs sc
                        WHERE pr.strategy_id = sc.id
                          AND sc.user_id = $1
                          AND pr.exchange_id = $2
                        """,
                        user_id,
                        exchange_name,
                    )
                    
                    logger.info(f"删除交易所配置...")
                    await conn.execute(
                        "DELETE FROM exchange_configs WHERE id = $1 AND user_id = $2", 
                        exchange_id,
                        user_id,
                    )
                    
                    # 3. 记录删除日志
                    await conn.execute("""
                        INSERT INTO deletion_logs 
                            (entity_type, entity_id, deletion_type, deleted_by, metadata)
                        VALUES ('exchange', $1, 'hard', $2, $3::jsonb)
                    """, exchange_id, user_id, {
                        'exchange_name': exchange_name,
                        'deleted_data': {
                            'orders': stats['orders'],
                            'pnl_records': stats['pnl_records'],
                            'strategies': stats['strategies']
                        }
                    })
                    
                    # 4. 记录系统日志
                    await conn.execute("""
                        INSERT INTO system_logs (user_id, level, source, message, extra)
                        VALUES ($1, 'CRITICAL', 'exchange_service', $2, $3::jsonb)
                    """, user_id, f"交易所已永久删除: {exchange_name}", {
                        'exchange_id': str(exchange_id),
                        'user_id': str(user_id),
                        'deleted_count': stats['orders'] + stats['pnl_records']
                    })
            
            # 5. 清理Redis缓存
            try:
                pattern = f"exchange:{exchange_name}:*"
                cursor = 0
                deleted = 0
                while True:
                    cursor, batch = await redis.scan(cursor=cursor, match=pattern, count=500)
                    if batch:
                        await redis.delete(*batch)
                        deleted += len(batch)
                    if cursor == 0:
                        break
                if deleted:
                    logger.info(f"✅ 已清理 {deleted} 个Redis缓存")
            except Exception as e:
                logger.warning(f"清理Redis缓存失败: {e}")
            
            logger.info(f"✅ 交易所已永久删除")
            
            return {
                'success': True,
                'deletion_type': 'hard',
                'data_retained': False,
                'deleted_data': {
                    'exchange_name': exchange_name,
                    'orders': stats['orders'],
                    'pnl_records': stats['pnl_records'],
                    'strategies_affected': stats['strategies']
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 硬删除失败: {e}")
            raise
