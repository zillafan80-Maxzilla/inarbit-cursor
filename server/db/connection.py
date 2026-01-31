"""
数据库连接层
提供 PostgreSQL 和 Redis 的统一连接管理
"""
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator
from dotenv import load_dotenv

# PostgreSQL 异步驱动
import asyncpg

# Redis 异步驱动
import redis.asyncio as redis

load_dotenv()
logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    数据库连接管理器
    负责 PostgreSQL 和 Redis 连接池的生命周期管理
    """
    
    _instance: Optional['DatabaseManager'] = None
    
    def __init__(self):
        # PostgreSQL 配置
        self.pg_host = os.getenv('POSTGRES_HOST', 'localhost')
        self.pg_port = int(os.getenv('POSTGRES_PORT', '5432'))
        self.pg_user = os.getenv('POSTGRES_USER', 'inarbit')
        self._default_pg_password = 'inarbit_secret_2026'
        self.pg_password = os.getenv('POSTGRES_PASSWORD', self._default_pg_password)
        self.pg_database = os.getenv('POSTGRES_DB', 'inarbit')
        self._pg_password_is_default = os.getenv('POSTGRES_PASSWORD') in {None, "", self._default_pg_password}
        
        # Redis 配置
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.redis_password = os.getenv('REDIS_PASSWORD', None)
        self.redis_db = int(os.getenv('REDIS_DB', '0'))
        
        # 连接池
        self._pg_pool: Optional[asyncpg.Pool] = None
        self._redis_client: Optional[redis.Redis] = None
        
    @classmethod
    def get_instance(cls) -> 'DatabaseManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = DatabaseManager()
        return cls._instance
    
    async def initialize(self):
        """
        初始化所有数据库连接
        优化: 添加连接池监控、慢查询日志
        """
        logger.info("正在初始化数据库连接...")

        try:
            pg_retries = int(os.getenv("PG_INIT_RETRIES", "5").strip() or "5")
        except Exception:
            pg_retries = 5
        try:
            pg_retry_delay = float(os.getenv("PG_INIT_RETRY_DELAY_SECONDS", "1").strip() or "1")
        except Exception:
            pg_retry_delay = 1.0
        try:
            pg_retry_max_delay = float(os.getenv("PG_INIT_RETRY_MAX_DELAY_SECONDS", "5").strip() or "5")
        except Exception:
            pg_retry_max_delay = 5.0

        # 使用默认密码时提示（避免生产误用）
        if self._pg_password_is_default:
            logger.warning("PostgreSQL 使用默认密码，请在生产环境设置 POSTGRES_PASSWORD")

        # 初始化 PostgreSQL 连接池
        last_error = None
        for attempt in range(1, max(1, pg_retries) + 1):
            try:
                self._pg_pool = await asyncpg.create_pool(
                    host=self.pg_host,
                    port=self.pg_port,
                    user=self.pg_user,
                    password=self.pg_password,
                    database=self.pg_database,
                    min_size=5,
                    max_size=20,
                    command_timeout=60,
                    # 添加连接初始化回调
                    init=self._init_connection
                )

                # 测试连接并获取版本信息
                async with self._pg_pool.acquire() as conn:
                    version = await conn.fetchval("SELECT version()")
                    db_size = await conn.fetchval("SELECT pg_database_size(current_database())")
                    logger.info(
                        f"✅ PostgreSQL 连接池已创建 ({self.pg_host}:{self.pg_port}) | "
                        f"连接池大小: 5-20 | "
                        f"数据库大小: {db_size / 1024 / 1024:.2f} MB"
                    )
                    logger.debug(f"PostgreSQL 版本: {version}")
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt >= pg_retries:
                    logger.error(f"❌ PostgreSQL 连接失败: {e}")
                    raise
                logger.warning(f"PostgreSQL 连接失败，{pg_retry_delay:.1f}s 后重试 ({attempt}/{pg_retries})")
                await asyncio.sleep(pg_retry_delay)
                pg_retry_delay = min(pg_retry_delay * 2, pg_retry_max_delay)
        
        try:
            redis_retries = int(os.getenv("REDIS_INIT_RETRIES", "5").strip() or "5")
        except Exception:
            redis_retries = 5
        try:
            redis_retry_delay = float(os.getenv("REDIS_INIT_RETRY_DELAY_SECONDS", "1").strip() or "1")
        except Exception:
            redis_retry_delay = 1.0
        try:
            redis_retry_max_delay = float(os.getenv("REDIS_INIT_RETRY_MAX_DELAY_SECONDS", "5").strip() or "5")
        except Exception:
            redis_retry_max_delay = 5.0

        # 初始化 Redis 连接
        for attempt in range(1, max(1, redis_retries) + 1):
            try:
                self._redis_client = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    password=self.redis_password,
                    db=self.redis_db,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    max_connections=200  # 增加连接池大小，避免并发任务耗尽连接
                )
                # 测试连接
                await self._redis_client.ping()

                # 获取 Redis 信息
                info = await self._redis_client.info('memory')
                used_memory = info.get('used_memory_human', 'Unknown')
                logger.info(
                    f"✅ Redis 连接已建立 ({self.redis_host}:{self.redis_port}) | "
                    f"内存使用: {used_memory}"
                )
                break
            except Exception as e:
                if attempt >= redis_retries:
                    logger.error(f"❌ Redis 连接失败: {e}")
                    raise
                logger.warning(f"Redis 连接失败，{redis_retry_delay:.1f}s 后重试 ({attempt}/{redis_retries})")
                await asyncio.sleep(redis_retry_delay)
                redis_retry_delay = min(redis_retry_delay * 2, redis_retry_max_delay)
        
        logger.info("🎉 所有数据库连接初始化完成")
    
    async def _init_connection(self, conn):
        """PostgreSQL 连接初始化回调 - 设置慢查询日志"""
        try:
            # 设置语句超时 (30秒)
            await conn.execute("SET statement_timeout = '30000'")
            # 启用慢查询日志 (超过100ms)
            await conn.execute("SET log_min_duration_statement = 100")
        except Exception as e:
            logger.warning(f"设置连接参数失败: {e}")

    
    async def close(self):
        """关闭所有连接"""
        logger.info("正在关闭数据库连接...")
        
        if self._pg_pool:
            await self._pg_pool.close()
            logger.info("PostgreSQL 连接池已关闭")
        
        if self._redis_client:
            close_fn = getattr(self._redis_client, "aclose", None)
            if callable(close_fn):
                await close_fn()
            else:
                await self._redis_client.close()
            logger.info("Redis 连接已关闭")
    
    @property
    def pg_pool(self) -> asyncpg.Pool:
        """获取 PostgreSQL 连接池"""
        if self._pg_pool is None:
            raise RuntimeError("PostgreSQL 连接池未初始化，请先调用 initialize()")
        return self._pg_pool
    
    @property
    def redis(self) -> redis.Redis:
        """获取 Redis 客户端"""
        if self._redis_client is None:
            raise RuntimeError("Redis 连接未初始化，请先调用 initialize()")
        return self._redis_client
    
    @asynccontextmanager
    async def pg_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """获取 PostgreSQL 连接的上下文管理器"""
        async with self.pg_pool.acquire() as conn:
            yield conn
    
    @asynccontextmanager
    async def pg_transaction(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """获取 PostgreSQL 事务连接的上下文管理器"""
        async with self.pg_pool.acquire() as conn:
            async with conn.transaction():
                yield conn


# ============================================
# 便捷函数
# ============================================

async def get_db() -> DatabaseManager:
    """获取数据库管理器实例"""
    db = DatabaseManager.get_instance()
    if db._pg_pool is None:
        await db.initialize()
    return db


async def get_pg_pool() -> asyncpg.Pool:
    """直接获取 PostgreSQL 连接池"""
    db = await get_db()
    return db.pg_pool


async def get_redis() -> redis.Redis:
    """直接获取 Redis 客户端"""
    db = DatabaseManager.get_instance()
    if db._redis_client is None:
        db._redis_client = redis.Redis(
            host=db.redis_host,
            port=db.redis_port,
            password=db.redis_password,
            db=db.redis_db,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            max_connections=200
        )
        await db._redis_client.ping()
    return db.redis


# ============================================
# 测试连接
# ============================================

async def test_connections():
    """测试所有数据库连接"""
    db = DatabaseManager.get_instance()
    
    try:
        await db.initialize()
        
        # 测试 PostgreSQL
        async with db.pg_connection() as conn:
            result = await conn.fetchval("SELECT current_database()")
            logger.info(f"PostgreSQL 测试成功，当前数据库: {result}")
        
        # 测试 Redis
        await db.redis.set("test_key", "test_value", ex=10)
        value = await db.redis.get("test_key")
        logger.info(f"Redis 测试成功，读取值: {value}")
        
        print("✅ 所有数据库连接测试通过!")
        
    except Exception as e:
        print(f"❌ 数据库连接测试失败: {e}")
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_connections())
