import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Iterable
from uuid import UUID, uuid4

from ..db import get_pg_pool, get_redis

logger = logging.getLogger(__name__)

STRATEGY_TYPES = {"graph", "grid", "pair"}


@dataclass
class TradingPair:
    symbol: str
    base: str
    quote: str
    is_active: bool = True
    supported_exchanges: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "base_currency": self.base,
            "quote_currency": self.quote,
            "is_active": self.is_active,
            "supported_exchanges": list(self.supported_exchanges or []),
        }


@dataclass
class ExchangeConfig:
    id: Optional[str]
    exchange_id: str
    display_name: Optional[str] = None
    is_active: bool = True
    deleted_at: Optional[Any] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None

    def to_dict(self) -> dict:
        return {
            "id": str(self.id) if self.id else None,
            "exchange_id": self.exchange_id,
            "display_name": self.display_name,
            "is_active": bool(self.is_active),
            "deleted_at": self.deleted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class OpportunityConfig:
    strategy_type: str
    config: dict
    version: int = 1
    updated_at: Optional[Any] = None

    def to_dict(self) -> dict:
        return {
            "strategyType": self.strategy_type,
            "strategy_type": self.strategy_type,
            "config": self.config,
            "version": int(self.version or 1),
            "updated_at": self.updated_at,
        }


DEFAULT_PAIRS = [
    TradingPair(symbol="BTC/USDT", base="BTC", quote="USDT", supported_exchanges=["binance"]),
    TradingPair(symbol="ETH/USDT", base="ETH", quote="USDT", supported_exchanges=["binance"]),
    TradingPair(symbol="BNB/USDT", base="BNB", quote="USDT", supported_exchanges=["binance"]),
    TradingPair(symbol="SOL/USDT", base="SOL", quote="USDT", supported_exchanges=["binance"]),
    TradingPair(symbol="XRP/USDT", base="XRP", quote="USDT", supported_exchanges=["binance"]),
]

DEFAULT_OPPORTUNITY_CONFIGS = {
    "graph": {"min_profit_rate": 0.002, "max_path_length": 5},
    "grid": {"grids": []},
    "pair": {
        "pair_a": "BTC/USDT",
        "pair_b": "ETH/USDT",
        "entry_z_score": 2.0,
        "exit_z_score": 0.5,
        "lookback_period": 100,
    },
}


class ConfigService:
    def __init__(self):
        self._cache: dict[str, tuple[float, Any]] = {}
        try:
            self._cache_ttl_seconds = float(os.getenv("CONFIG_CACHE_TTL_SECONDS", "30").strip() or "30")
        except Exception:
            self._cache_ttl_seconds = 30.0

    def _validate_strategy_type(self, strategy_type: str) -> str:
        if not strategy_type:
            raise ValueError("strategy_type is required")
        st = str(strategy_type).strip().lower()
        if st not in STRATEGY_TYPES:
            raise ValueError(f"unsupported strategy_type: {strategy_type}")
        return st

    def _validate_opportunity_config(self, strategy_type: str, config: dict) -> None:
        st = self._validate_strategy_type(strategy_type)
        if not isinstance(config, dict):
            raise ValueError("config must be a dict")

        def _is_number(value: Any) -> bool:
            return isinstance(value, (int, float)) and not isinstance(value, bool)

        if st == "graph":
            min_profit_rate = config.get("min_profit_rate", 0.0)
            if not _is_number(min_profit_rate):
                raise ValueError("min_profit_rate must be a number")
            max_path_length = config.get("max_path_length", 3)
            if not isinstance(max_path_length, int) or max_path_length < 2:
                raise ValueError("max_path_length must be >= 2")

        if st == "grid":
            grids = config.get("grids")
            if grids is None:
                grids = []
            if not isinstance(grids, list):
                raise ValueError("grids must be a list")
            for g in grids:
                if not isinstance(g, dict):
                    raise ValueError("grid item must be a dict")
                if not isinstance(g.get("symbol"), str):
                    raise ValueError("grid.symbol is required")
                if not _is_number(g.get("upper_price")):
                    raise ValueError("grid.upper_price must be a number")
                if not _is_number(g.get("lower_price")):
                    raise ValueError("grid.lower_price must be a number")
                if not isinstance(g.get("grid_count"), int) or g.get("grid_count") < 2:
                    raise ValueError("grid.grid_count must be >= 2")

        if st == "pair":
            if not isinstance(config.get("pair_a"), str):
                raise ValueError("pair_a is required")
            if not isinstance(config.get("pair_b"), str):
                raise ValueError("pair_b is required")
            entry_z = config.get("entry_z_score", 2.0)
            exit_z = config.get("exit_z_score", 0.5)
            if not _is_number(entry_z) or not _is_number(exit_z):
                raise ValueError("entry_z_score/exit_z_score must be numbers")
            lookback = config.get("lookback_period", 100)
            if not isinstance(lookback, int) or lookback < 2:
                raise ValueError("lookback_period must be >= 2")

    async def refresh_cache(self) -> None:
        self._cache.clear()

    async def _table_exists(self, conn, table_name: str) -> bool:
        return bool(
            await conn.fetchval(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = $1
                """,
                table_name,
            )
        )

    def _cache_get(self, key: str) -> Optional[Any]:
        item = self._cache.get(key)
        if not item:
            return None
        ts, value = item
        if (datetime.utcnow().timestamp() - ts) > self._cache_ttl_seconds:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        self._cache[key] = (datetime.utcnow().timestamp(), value)

    async def get_all_exchanges(self, *, user_id: Optional[UUID] = None) -> list[ExchangeConfig]:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            if not await self._table_exists(conn, "exchange_configs"):
                return []
            if user_id:
                rows = await conn.fetch("SELECT * FROM exchange_configs WHERE user_id = $1", user_id)
            else:
                rows = await conn.fetch("SELECT * FROM exchange_configs")
        result: list[ExchangeConfig] = []
        for row in rows or []:
            data = dict(row)
            result.append(
                ExchangeConfig(
                    id=data.get("id"),
                    exchange_id=data.get("exchange_id") or data.get("exchange"),
                    display_name=data.get("display_name"),
                    is_active=bool(data.get("is_active", True)),
                    deleted_at=data.get("deleted_at"),
                    created_at=data.get("created_at"),
                    updated_at=data.get("updated_at"),
                )
            )
        return result

    async def get_connected_exchanges(self, *, user_id: Optional[UUID] = None) -> list[ExchangeConfig]:
        exchanges = await self.get_all_exchanges(user_id=user_id)
        out = []
        for ex in exchanges:
            if not ex.is_active:
                continue
            if ex.deleted_at:
                continue
            out.append(ex)
        return out

    async def get_exchange(self, exchange_id: str, *, user_id: Optional[UUID] = None) -> Optional[ExchangeConfig]:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            if not await self._table_exists(conn, "exchange_configs"):
                return None
            params = [exchange_id]
            where = "exchange_id = $1"
            try:
                uid = UUID(exchange_id)
                where = "id = $1"
                params = [uid]
            except Exception:
                pass
            if user_id:
                params.append(user_id)
                where = f"{where} AND user_id = ${len(params)}"
            row = await conn.fetchrow(f"SELECT * FROM exchange_configs WHERE {where} LIMIT 1", *params)
        if not row:
            return None
        data = dict(row)
        return ExchangeConfig(
            id=data.get("id"),
            exchange_id=data.get("exchange_id") or data.get("exchange"),
            display_name=data.get("display_name"),
            is_active=bool(data.get("is_active", True)),
            deleted_at=data.get("deleted_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    async def get_all_pairs(self) -> list[TradingPair]:
        cache_key = "pairs:all"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        pool = await get_pg_pool()
        pairs: list[TradingPair] = []
        async with pool.acquire() as conn:
            if await self._table_exists(conn, "trading_pairs"):
                rows = await conn.fetch("SELECT * FROM trading_pairs WHERE is_active = true")
                for row in rows or []:
                    data = dict(row)
                    pairs.append(
                        TradingPair(
                            symbol=data.get("symbol"),
                            base=data.get("base_currency") or data.get("base"),
                            quote=data.get("quote_currency") or data.get("quote"),
                            is_active=bool(data.get("is_active", True)),
                            supported_exchanges=data.get("supported_exchanges") or [],
                        )
                    )

        if not pairs:
            pairs = list(DEFAULT_PAIRS)
        self._cache_set(cache_key, pairs)
        return pairs

    async def get_pairs_for_exchange(
        self,
        exchange_id: str,
        *,
        user_id: Optional[UUID] = None,
        enabled_only: bool = False,
    ) -> list[TradingPair]:
        cache_key = f"pairs:exchange:{exchange_id}:{user_id}:{enabled_only}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        pool = await get_pg_pool()
        pairs: list[TradingPair] = []
        async with pool.acquire() as conn:
            has_trading_pairs = await self._table_exists(conn, "trading_pairs")
            has_exchange_configs = await self._table_exists(conn, "exchange_configs")
            has_exchange_pairs = await self._table_exists(conn, "exchange_trading_pairs")
            if has_trading_pairs and has_exchange_configs and has_exchange_pairs:
                params: list[Any] = []
                where_clause = []
                try:
                    exchange_uuid = UUID(exchange_id)
                    where_clause.append("ec.id = $1")
                    params.append(exchange_uuid)
                except Exception:
                    where_clause.append("ec.exchange_id = $1")
                    params.append(exchange_id)
                if user_id:
                    where_clause.append(f"ec.user_id = ${len(params) + 1}")
                    params.append(user_id)
                if enabled_only:
                    where_clause.append("etp.is_enabled = true")
                where_clause.append("tp.is_active = true")
                where_sql = " AND ".join(where_clause)
                rows = await conn.fetch(
                    f"""
                    SELECT tp.symbol, tp.base_currency, tp.quote_currency, tp.is_active, tp.supported_exchanges
                    FROM exchange_trading_pairs etp
                    JOIN trading_pairs tp ON tp.id = etp.trading_pair_id
                    JOIN exchange_configs ec ON ec.id = etp.exchange_config_id
                    WHERE {where_sql}
                    """,
                    *params,
                )
                for row in rows or []:
                    data = dict(row)
                    pairs.append(
                        TradingPair(
                            symbol=data.get("symbol"),
                            base=data.get("base_currency") or data.get("base"),
                            quote=data.get("quote_currency") or data.get("quote"),
                            is_active=bool(data.get("is_active", True)),
                            supported_exchanges=data.get("supported_exchanges") or [],
                        )
                    )

        if not pairs:
            # 如果交易所配置已存在（即用户已接入/创建过该交易所），就不要用默认交易对制造“看似存在币对”的假象
            try:
                ex = await self.get_exchange(exchange_id, user_id=user_id)
            except Exception:
                ex = None
            if ex is None:
                fallback = []
                for p in DEFAULT_PAIRS:
                    if p.supported_exchanges and exchange_id not in p.supported_exchanges:
                        continue
                    if enabled_only and not p.is_active:
                        continue
                    fallback.append(p)
                pairs = fallback

        self._cache_set(cache_key, pairs)
        return pairs

    async def get_pair(self, symbol: str) -> Optional[TradingPair]:
        symbol = symbol.strip()
        if not symbol:
            return None
        pairs = await self.get_all_pairs()
        for p in pairs:
            if p.symbol == symbol:
                return p
        return None

    async def get_base_currencies(self) -> list[str]:
        pairs = await self.get_all_pairs()
        bases = {p.base for p in pairs if p.base}
        return sorted(bases)

    async def _load_opportunity_from_redis(self, user_id: UUID, strategy_type: str) -> OpportunityConfig:
        redis = await get_redis()
        key = f"config:opportunity:{user_id}:{strategy_type}"
        raw = await redis.get(key)
        if raw:
            try:
                payload = json.loads(raw)
                return OpportunityConfig(
                    strategy_type=strategy_type,
                    config=payload.get("config") or {},
                    version=int(payload.get("version") or 1),
                    updated_at=payload.get("updated_at"),
                )
            except Exception:
                pass
        default_cfg = DEFAULT_OPPORTUNITY_CONFIGS.get(strategy_type, {})
        return OpportunityConfig(strategy_type=strategy_type, config=default_cfg, version=1)

    async def get_opportunity_config(self, *, strategy_type: str, user_id: UUID) -> OpportunityConfig:
        st = self._validate_strategy_type(strategy_type)
        return await self._load_opportunity_from_redis(user_id, st)

    async def get_all_opportunity_configs(self, *, user_id: UUID) -> list[OpportunityConfig]:
        result = []
        for st in STRATEGY_TYPES:
            result.append(await self.get_opportunity_config(strategy_type=st, user_id=user_id))
        return result

    async def _record_history(self, user_id: UUID, strategy_type: str, version: int, config: dict) -> None:
        redis = await get_redis()
        history_key = f"config:opportunity:history:{user_id}:{strategy_type}"
        record = {
            "version": version,
            "config": config,
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            pipe = redis.pipeline()
            pipe.lpush(history_key, json.dumps(record, ensure_ascii=False))
            pipe.ltrim(history_key, 0, 200)
            await pipe.execute()
        except Exception:
            pass

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            if await self._table_exists(conn, "opportunity_config_history"):
                await conn.execute(
                    """
                    INSERT INTO opportunity_config_history (user_id, strategy_type, version, config)
                    VALUES ($1, $2, $3, $4::jsonb)
                    """,
                    user_id,
                    strategy_type,
                    version,
                    json.dumps(config, ensure_ascii=False),
                )

    async def update_opportunity_config(self, *, strategy_type: str, config: dict, user_id: UUID) -> OpportunityConfig:
        st = self._validate_strategy_type(strategy_type)
        self._validate_opportunity_config(st, config)

        current = await self._load_opportunity_from_redis(user_id, st)
        version = int(current.version or 1) + 1

        redis = await get_redis()
        key = f"config:opportunity:{user_id}:{st}"
        payload = {
            "config": config,
            "version": version,
            "updated_at": datetime.utcnow().isoformat(),
        }
        await redis.set(key, json.dumps(payload, ensure_ascii=False))
        await self._record_history(user_id, st, version, config)
        return OpportunityConfig(strategy_type=st, config=config, version=version, updated_at=payload["updated_at"])

    async def list_opportunity_config_history(self, *, strategy_type: str, user_id: UUID, limit: int = 20) -> list[dict]:
        st = self._validate_strategy_type(strategy_type)
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            if await self._table_exists(conn, "opportunity_config_history"):
                rows = await conn.fetch(
                    """
                    SELECT id, version, config, created_at
                    FROM opportunity_config_history
                    WHERE user_id = $1 AND strategy_type = $2
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    user_id,
                    st,
                    max(1, min(200, limit)),
                )
                return [dict(r) for r in rows]

        redis = await get_redis()
        history_key = f"config:opportunity:history:{user_id}:{st}"
        rows = await redis.lrange(history_key, 0, max(0, limit - 1))
        items = []
        for raw in rows or []:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")
            if isinstance(raw, str):
                try:
                    items.append(json.loads(raw))
                except Exception:
                    items.append({"raw": raw})
        return items

    async def rollback_opportunity_config(self, *, strategy_type: str, version: int, user_id: UUID) -> OpportunityConfig:
        st = self._validate_strategy_type(strategy_type)
        target_cfg = None

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            if await self._table_exists(conn, "opportunity_config_history"):
                row = await conn.fetchrow(
                    """
                    SELECT config
                    FROM opportunity_config_history
                    WHERE user_id = $1 AND strategy_type = $2 AND version = $3
                    """,
                    user_id,
                    st,
                    version,
                )
                if row:
                    target_cfg = dict(row).get("config")

        if target_cfg is None:
            redis = await get_redis()
            history_key = f"config:opportunity:history:{user_id}:{st}"
            rows = await redis.lrange(history_key, 0, -1)
            for raw in rows or []:
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if int(payload.get("version") or 0) == int(version):
                    target_cfg = payload.get("config")
                    break

        if target_cfg is None:
            raise ValueError("version not found")

        return await self.update_opportunity_config(strategy_type=st, config=target_cfg, user_id=user_id)

    async def list_opportunity_templates(self, *, strategy_type: Optional[str] = None) -> list[dict]:
        st = None
        if strategy_type:
            st = self._validate_strategy_type(strategy_type)

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            if await self._table_exists(conn, "opportunity_config_templates"):
                if st:
                    rows = await conn.fetch(
                        """
                        SELECT id, strategy_type, name, description, config, created_by, created_at
                        FROM opportunity_config_templates
                        WHERE strategy_type = $1
                        ORDER BY created_at DESC
                        """,
                        st,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, strategy_type, name, description, config, created_by, created_at
                        FROM opportunity_config_templates
                        ORDER BY created_at DESC
                        """
                    )
                return [dict(r) for r in rows]

        redis = await get_redis()
        key = f"config:opportunity:templates:{st or 'all'}"
        rows = await redis.lrange(key, 0, -1)
        items = []
        for raw in rows or []:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")
            try:
                items.append(json.loads(raw))
            except Exception:
                items.append({"raw": raw})
        if st:
            items = [i for i in items if str(i.get("strategy_type")) == st]
        return items

    async def create_opportunity_template(
        self,
        *,
        strategy_type: str,
        name: str,
        description: str,
        config: dict,
        user_id: UUID,
    ) -> dict:
        st = self._validate_strategy_type(strategy_type)
        self._validate_opportunity_config(st, config)
        if not name:
            raise ValueError("name is required")

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            if await self._table_exists(conn, "opportunity_config_templates"):
                row = await conn.fetchrow(
                    """
                    INSERT INTO opportunity_config_templates (strategy_type, name, description, config, created_by)
                    VALUES ($1, $2, $3, $4::jsonb, $5)
                    RETURNING id, strategy_type, name, description, config, created_by, created_at
                    """,
                    st,
                    name,
                    description,
                    json.dumps(config, ensure_ascii=False),
                    user_id,
                )
                return dict(row)

        template = {
            "id": str(uuid4()),
            "strategy_type": st,
            "name": name,
            "description": description,
            "config": config,
            "created_by": str(user_id),
            "created_at": datetime.utcnow().isoformat(),
        }
        redis = await get_redis()
        key = f"config:opportunity:templates:{st}"
        await redis.lpush(key, json.dumps(template, ensure_ascii=False))
        return template

    async def apply_opportunity_template(
        self,
        *,
        template_id: UUID,
        strategy_type: str,
        user_id: UUID,
    ) -> OpportunityConfig:
        st = self._validate_strategy_type(strategy_type)

        templates = await self.list_opportunity_templates(strategy_type=st)
        template = None
        for t in templates:
            if str(t.get("id")) == str(template_id):
                template = t
                break
        if not template:
            raise ValueError("template not found")

        cfg = template.get("config") or {}
        return await self.update_opportunity_config(strategy_type=st, config=cfg, user_id=user_id)


_config_service: Optional[ConfigService] = None


async def get_config_service() -> ConfigService:
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service
