"""
统一配置服务
提供交易所、币种、全局设置的统一访问接口
确保所有模块使用相同的数据源，避免配置不一致导致系统崩溃
"""
import json
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..db import get_pg_pool, get_redis

logger = logging.getLogger(__name__)


# ============================================
# 数据模型
# ============================================

@dataclass
class ExchangeConfig:
    """交易所配置"""
    id: str
    name: str
    icon: str
    bg_color: str
    border_color: str
    is_connected: bool = False
    is_spot_enabled: bool = True
    is_futures_enabled: bool = False
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'icon': self.icon,
            'bgColor': self.bg_color,
            'borderColor': self.border_color,
            'isConnected': self.is_connected,
            'isSpotEnabled': self.is_spot_enabled,
            'isFuturesEnabled': self.is_futures_enabled
        }


@dataclass
class TradingPair:
    """交易对配置"""
    symbol: str
    base: str
    quote: str
    is_active: bool = True
    supported_exchanges: List[str] = None
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'base': self.base,
            'quote': self.quote,
            'isActive': self.is_active,
            'supportedExchanges': self.supported_exchanges or []
        }


@dataclass
class OpportunityConfig:
    """机会配置"""
    strategy_type: str
    config: dict
    version: int
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "strategyType": self.strategy_type,
            "config": self.config,
            "version": self.version,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================
# 默认配置（用于初始化）
# ============================================

DEFAULT_EXCHANGES = [
    ExchangeConfig('binance', 'Binance', '🟡', 'rgba(181, 137, 0, 0.12)', '#b58900'),
    ExchangeConfig('okx', 'OKX', '⚪', 'rgba(131, 148, 150, 0.12)', '#839496'),
    ExchangeConfig('bybit', 'Bybit', '🟠', 'rgba(203, 75, 22, 0.10)', '#cb4b16'),
    ExchangeConfig('gate', 'Gate.io', '🔵', 'rgba(38, 139, 210, 0.10)', '#268bd2'),
    ExchangeConfig('bitget', 'Bitget', '🟢', 'rgba(133, 153, 0, 0.10)', '#859900'),
]

DEFAULT_PAIRS = [
    TradingPair('BTC/USDT', 'BTC', 'USDT', True, ['binance', 'okx', 'bybit', 'gate']),
    TradingPair('ETH/USDT', 'ETH', 'USDT', True, ['binance', 'okx', 'bybit', 'gate']),
    TradingPair('BNB/USDT', 'BNB', 'USDT', True, ['binance']),
    TradingPair('SOL/USDT', 'SOL', 'USDT', True, ['binance', 'okx', 'bybit']),
    TradingPair('XRP/USDT', 'XRP', 'USDT', True, ['binance', 'okx', 'bybit', 'gate']),
    TradingPair('DOGE/USDT', 'DOGE', 'USDT', True, ['binance', 'okx']),
    TradingPair('BEAM/USDT', 'BEAM', 'USDT', True, ['binance']),
    TradingPair('BSW/USDT', 'BSW', 'USDT', True, ['binance']),
    TradingPair('ANC/USDT', 'ANC', 'USDT', True, ['binance']),
    TradingPair('AGIX/USDT', 'AGIX', 'USDT', True, ['binance']),
    TradingPair('BLZ/USDT', 'BLZ', 'USDT', True, ['binance']),
]


# ============================================
# 配置服务类
# ============================================

class ConfigService:
    """
    统一配置服务 - 单例模式
    确保所有模块使用相同的配置数据
    """
    
    _instance: Optional['ConfigService'] = None
    CACHE_TTL = 300  # 缓存5分钟
    
    def __init__(self):
        self._exchanges_cache: Dict[str, ExchangeConfig] = {}
        self._pairs_cache: Dict[str, TradingPair] = {}
        self._opportunity_cache: Dict[str, Dict[str, OpportunityConfig]] = {}
        self._cache_time: Optional[datetime] = None
    
    @classmethod
    def get_instance(cls) -> 'ConfigService':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = ConfigService()
        return cls._instance
    
    async def initialize(self):
        """初始化配置服务，从数据库加载配置"""
        logger.info("正在初始化配置服务...")
        await self._load_from_database()
        logger.info("配置服务初始化完成")
    
    async def _load_from_database(self):
        """从数据库加载配置"""
        try:
            pool = await get_pg_pool()
            
            # 加载交易所配置
            async with pool.acquire() as conn:
                # 检查exchange_status表是否存在
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'exchange_status'
                    )
                """)
                
                if exists:
                    rows = await conn.fetch("SELECT * FROM exchange_status")
                    if not rows:
                        logger.info("exchange_status表为空，使用默认配置")
                        for ex in DEFAULT_EXCHANGES:
                            self._exchanges_cache[ex.id] = ex
                    else:
                        for row in rows:
                            self._exchanges_cache[row['exchange_id']] = ExchangeConfig(
                                id=row['exchange_id'],
                                name=row['display_name'],
                                icon=row['icon'],
                                bg_color=row['bg_color'] if 'bg_color' in row and row['bg_color'] else 'rgba(0,0,0,0.1)',
                                border_color=row['border_color'] if 'border_color' in row and row['border_color'] else '#666',
                                is_connected=row['is_connected'] if 'is_connected' in row and row['is_connected'] is not None else False
                            )
                else:
                    # 使用默认配置
                    logger.info("exchange_status表不存在，使用默认配置")
                    for ex in DEFAULT_EXCHANGES:
                        self._exchanges_cache[ex.id] = ex
                
                # 检查trading_pairs表是否存在
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'trading_pairs'
                    )
                """)
                
                if exists:
                    rows = await conn.fetch("SELECT * FROM trading_pairs WHERE is_active = true")
                    if not rows:
                        logger.info("trading_pairs表为空，使用默认配置")
                        for pair in DEFAULT_PAIRS:
                            self._pairs_cache[pair.symbol] = pair
                    else:
                        for row in rows:
                            self._pairs_cache[row['symbol']] = TradingPair(
                                symbol=row['symbol'],
                                base=row['base_currency'],
                                quote=row['quote_currency'],
                                is_active=row['is_active'],
                                supported_exchanges=row['supported_exchanges'] if 'supported_exchanges' in row and row['supported_exchanges'] else []
                            )
                else:
                    # 使用默认配置
                    logger.info("trading_pairs表不存在，使用默认配置")
                    for pair in DEFAULT_PAIRS:
                        self._pairs_cache[pair.symbol] = pair
            
            self._cache_time = datetime.now()
            logger.info(f"已加载 {len(self._exchanges_cache)} 个交易所, {len(self._pairs_cache)} 个交易对")
            
        except Exception as e:
            logger.warning(f"从数据库加载配置失败，使用默认配置: {e}")
            # 使用默认配置
            for ex in DEFAULT_EXCHANGES:
                self._exchanges_cache[ex.id] = ex
            for pair in DEFAULT_PAIRS:
                self._pairs_cache[pair.symbol] = pair

    async def _load_opportunity_configs(self, user_id: UUID):
        """从数据库加载机会配置并同步到 Redis"""
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT strategy_type, config, version, updated_at
                FROM opportunity_configs
                WHERE user_id = $1 AND is_active = true
                """,
                user_id,
            )

        configs: Dict[str, OpportunityConfig] = {}
        for row in rows or []:
            config_value = row["config"] or {}
            if isinstance(config_value, str):
                try:
                    config_value = json.loads(config_value)
                except Exception:
                    config_value = {}
            configs[str(row["strategy_type"])] = OpportunityConfig(
                strategy_type=str(row["strategy_type"]),
                config=config_value,
                version=int(row["version"] or 1),
                updated_at=row.get("updated_at"),
            )

        self._opportunity_cache[str(user_id)] = configs
        await self._sync_opportunity_configs_to_redis(user_id, configs)

    async def _sync_opportunity_configs_to_redis(self, user_id: UUID, configs: Dict[str, OpportunityConfig]):
        redis = await get_redis()
        for strategy_type, cfg in configs.items():
            key = f"config:opportunity:{user_id}:{strategy_type}"
            await redis.set(key, json.dumps(cfg.to_dict(), ensure_ascii=False))

    def _validate_strategy_type(self, strategy_type: str) -> str:
        allowed = {"graph", "grid", "pair"}
        normalized = (strategy_type or "").strip().lower()
        if normalized not in allowed:
            raise ValueError(f"unsupported strategy_type: {strategy_type}")
        return normalized
    
    # ============================================
    # 交易所配置接口
    # ============================================

    async def _get_user_connected_exchange_ids(self, user_id: UUID) -> set[str]:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT exchange_id
                FROM exchange_configs
                WHERE user_id = $1 AND is_active = true
                """,
                user_id,
            )
        return {r["exchange_id"] for r in rows}
    
    async def get_all_exchanges(self, user_id: Optional[UUID] = None) -> List[ExchangeConfig]:
        """获取所有交易所配置"""
        if not self._exchanges_cache or not self.is_cache_valid():
            await self._load_from_database()

        exchanges = list(self._exchanges_cache.values())
        if not user_id:
            return exchanges

        connected_ids = await self._get_user_connected_exchange_ids(user_id)
        return [
            ExchangeConfig(
                id=ex.id,
                name=ex.name,
                icon=ex.icon,
                bg_color=ex.bg_color,
                border_color=ex.border_color,
                is_connected=ex.id in connected_ids,
                is_spot_enabled=ex.is_spot_enabled,
                is_futures_enabled=ex.is_futures_enabled,
            )
            for ex in exchanges
        ]
    
    async def get_exchange(self, exchange_id: str, user_id: Optional[UUID] = None) -> Optional[ExchangeConfig]:
        """获取指定交易所配置"""
        if not self._exchanges_cache or not self.is_cache_valid():
            await self._load_from_database()

        ex = self._exchanges_cache.get(exchange_id)
        if not ex:
            return None
        if not user_id:
            return ex

        connected_ids = await self._get_user_connected_exchange_ids(user_id)
        return ExchangeConfig(
            id=ex.id,
            name=ex.name,
            icon=ex.icon,
            bg_color=ex.bg_color,
            border_color=ex.border_color,
            is_connected=ex.id in connected_ids,
            is_spot_enabled=ex.is_spot_enabled,
            is_futures_enabled=ex.is_futures_enabled,
        )
    
    async def get_connected_exchanges(self, user_id: Optional[UUID] = None) -> List[ExchangeConfig]:
        """获取已连接的交易所"""
        all_exchanges = await self.get_all_exchanges(user_id=user_id)
        return [ex for ex in all_exchanges if ex.is_connected]
    
    async def set_exchange_connected(self, exchange_id: str, connected: bool):
        """设置交易所连接状态"""
        if exchange_id in self._exchanges_cache:
            self._exchanges_cache[exchange_id].is_connected = connected
            
            return
    
    # ============================================
    # 交易对配置接口
    # ============================================

    async def _get_exchange_config_id(self, user_id: UUID, exchange_id: str) -> Optional[UUID]:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT id
                FROM exchange_configs
                WHERE user_id = $1 AND exchange_id = $2 AND is_active = true
                ORDER BY created_at DESC
                LIMIT 1
                """,
                user_id,
                exchange_id,
            )

    async def _get_pairs_for_exchange_user(self, user_id: UUID, exchange_id: str, enabled_only: bool = False) -> List[TradingPair]:
        exchange_config_id = await self._get_exchange_config_id(user_id, exchange_id)
        if not exchange_config_id:
            return []

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = """
                SELECT tp.symbol, tp.base_currency, tp.quote_currency, tp.is_active, tp.supported_exchanges
                FROM exchange_trading_pairs etp
                JOIN trading_pairs tp ON tp.id = etp.trading_pair_id
                WHERE etp.exchange_config_id = $1
            """
            if enabled_only:
                query += " AND etp.is_enabled = true"

            rows = await conn.fetch(query, exchange_config_id)

        return [
            TradingPair(
                symbol=r["symbol"],
                base=r["base_currency"],
                quote=r["quote_currency"],
                is_active=r["is_active"],
                supported_exchanges=r["supported_exchanges"] or [],
            )
            for r in rows
        ]
    
    async def get_all_pairs(self) -> List[TradingPair]:
        """获取所有交易对"""
        if not self._pairs_cache or not self.is_cache_valid():
            await self._load_from_database()
        return list(self._pairs_cache.values())
    
    async def get_pair(self, symbol: str) -> Optional[TradingPair]:
        """获取指定交易对"""
        if not self._pairs_cache or not self.is_cache_valid():
            await self._load_from_database()
        return self._pairs_cache.get(symbol)
    
    async def get_pairs_for_exchange(
        self,
        exchange_id: str,
        user_id: Optional[UUID] = None,
        enabled_only: bool = False,
    ) -> List[TradingPair]:
        """获取指定交易所支持的交易对"""
        if user_id:
            return await self._get_pairs_for_exchange_user(user_id, exchange_id, enabled_only=enabled_only)

        all_pairs = await self.get_all_pairs()
        # supported_exchanges 为空时表示“所有交易所均可用”
        return [p for p in all_pairs if (not (p.supported_exchanges or [])) or exchange_id in (p.supported_exchanges or [])]
    
    async def get_base_currencies(self) -> List[str]:
        """获取所有基础货币列表"""
        all_pairs = await self.get_all_pairs()
        return list(set(p.base for p in all_pairs))

    # ============================================
    # 机会配置接口
    # ============================================

    async def get_opportunity_config(self, strategy_type: str, user_id: UUID) -> OpportunityConfig:
        normalized = self._validate_strategy_type(strategy_type)
        user_key = str(user_id)
        if user_key not in self._opportunity_cache:
            await self._load_opportunity_configs(user_id)

        cache = self._opportunity_cache.get(user_key) or {}
        if normalized in cache:
            return cache[normalized]

        return OpportunityConfig(strategy_type=normalized, config={}, version=1, updated_at=None)

    async def get_all_opportunity_configs(self, user_id: UUID) -> List[OpportunityConfig]:
        user_key = str(user_id)
        if user_key not in self._opportunity_cache:
            await self._load_opportunity_configs(user_id)
        return list((self._opportunity_cache.get(user_key) or {}).values())

    async def update_opportunity_config(self, strategy_type: str, config: dict, user_id: UUID) -> OpportunityConfig:
        normalized = self._validate_strategy_type(strategy_type)
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO opportunity_configs (user_id, strategy_type, config, version, is_active, updated_at)
                VALUES ($1, $2::strategy_type, $3::jsonb, 1, true, NOW())
                ON CONFLICT (user_id, strategy_type) DO UPDATE SET
                    config = EXCLUDED.config,
                    version = opportunity_configs.version + 1,
                    is_active = true,
                    updated_at = NOW()
                RETURNING strategy_type, config, version, updated_at
                """,
                user_id,
                normalized,
                json.dumps(config, ensure_ascii=False),
            )

        if not row:
            raise RuntimeError("failed to update opportunity config")

        config_value = row["config"] or {}
        if isinstance(config_value, str):
            try:
                config_value = json.loads(config_value)
            except Exception:
                config_value = {}

        updated = OpportunityConfig(
            strategy_type=str(row["strategy_type"]),
            config=config_value,
            version=int(row["version"] or 1),
            updated_at=row.get("updated_at"),
        )

        user_key = str(user_id)
        if user_key not in self._opportunity_cache:
            self._opportunity_cache[user_key] = {}
        self._opportunity_cache[user_key][normalized] = updated
        await self._sync_opportunity_configs_to_redis(user_id, {normalized: updated})
        return updated
    
    # ============================================
    # 缓存管理
    # ============================================
    
    async def refresh_cache(self):
        """刷新缓存"""
        self._exchanges_cache.clear()
        self._pairs_cache.clear()
        self._opportunity_cache.clear()
        await self._load_from_database()
    
    def is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if self._cache_time is None:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self.CACHE_TTL


# ============================================
# 便捷函数
# ============================================

async def get_config_service() -> ConfigService:
    """获取配置服务实例"""
    service = ConfigService.get_instance()
    if not service._exchanges_cache or not service.is_cache_valid():
        await service.initialize()
    return service