import asyncio
import json
import logging
import time
import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set
from decimal import Decimal

from ..db import get_redis, get_pg_pool
from .market_data_repository import MarketDataRepository
from .market_regime_service import MarketRegimeService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskConstraints:
    """人为可配置的避险约束"""
    max_exposure_per_symbol: Decimal = Decimal('1000')      # 单币种最大敞口（USDT）
    max_total_exposure: Decimal = Decimal('5000')          # 总敞口上限
    min_profit_rate: Decimal = Decimal('0.001')           # 最小收益率阈值
    max_positions: int = 5                                 # 最大同时持仓数
    blacklist_symbols: Set[str] = field(default_factory=set)  # 黑名单币种
    whitelist_symbols: Set[str] = field(default_factory=set)  # 白名单币种（若非空则只选这些）
    max_drawdown_per_symbol: Decimal = Decimal('0.05')     # 单币种最大回撤
    liquidity_score_min: Decimal = Decimal('0.5')         # 最小流动性评分
    max_spread_rate: Decimal = Decimal('0.002')            # 允许的最大点差比例（ask-bid)/mid
    max_data_age_ms: int = 15000                           # 行情/盘口数据最大允许延迟
    min_confidence: Decimal = Decimal('0.50')              # 置信度阈值（过低直接过滤）
    max_abs_funding_rate: Decimal = Decimal('0.02')        # 资金费率绝对值上限（防止异常尖刺）


@dataclass(frozen=True)
class Decision:
    """决策输出"""
    strategy_type: str  # triangular/cashcarry
    exchange_id: str
    symbol: str
    direction: str
    expected_profit_rate: Decimal
    estimated_exposure: Decimal
    risk_score: Decimal
    confidence: Decimal
    timestamp_ms: int
    raw_opportunity: dict  # 原始机会数据
    regime: Optional[str] = None
    routing_weight: Optional[Decimal] = None

    def to_redis_member(self) -> str:
        return json.dumps(
            {
                "strategyType": self.strategy_type,
                "exchange": self.exchange_id,
                "symbol": self.symbol,
                "direction": self.direction,
                "expectedProfitRate": str(self.expected_profit_rate),
                "estimatedExposure": str(self.estimated_exposure),
                "riskScore": str(self.risk_score),
                "confidence": str(self.confidence),
                "timestamp": self.timestamp_ms,
                "rawOpportunity": self.raw_opportunity,
                "regime": self.regime,
                "routingWeight": str(self.routing_weight) if self.routing_weight is not None else None,
            },
            ensure_ascii=False,
        )


class DecisionService:
    """决策器/调度器：从机会中选出符合避险约束的最优执行方案"""

    def __init__(
        self,
        exchange_id: str = "binance",
        refresh_interval_seconds: float = 2.0,
        ttl_seconds: int = 10,
        max_decisions: int = 10,
    ):
        self.exchange_id = exchange_id
        try:
            env_interval = float(os.getenv("DECISION_REFRESH_INTERVAL", "").strip() or 0)
        except Exception:
            env_interval = 0
        self.refresh_interval_seconds = env_interval if env_interval > 0 else refresh_interval_seconds
        self.ttl_seconds = ttl_seconds
        self.max_decisions = max_decisions

        self._constraints: RiskConstraints = RiskConstraints()
        self._auto_overlay: dict = {
            "timestamp_ms": 0,
            "min_profit_rate_boost": "0",
            "exposure_multiplier": "1",
            "blacklist_symbols": [],
        }
        self._repo = MarketDataRepository()
        self._regime_service = MarketRegimeService(exchange_id=exchange_id)
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._last_log_ts: float = 0.0
        self._last_decision_count: Optional[int] = None
        self._routing_cache: dict = {}
        self._routing_cache_ts: int = 0
        try:
            self._routing_cache_ttl_ms = int(os.getenv("DECISION_ROUTING_CACHE_TTL_MS", "10000").strip() or "10000")
        except Exception:
            self._routing_cache_ttl_ms = 10000

        self._constraints_key = "decision:constraints:human"
        self._auto_constraints_key = "decision:constraints:auto"
        self._effective_constraints_key = "decision:constraints:effective"
        try:
            self._concurrency = int(os.getenv("DECISION_CONCURRENCY", "20").strip() or "20")
        except Exception:
            self._concurrency = 20
        try:
            self._auto_overlay_interval_ms = int(os.getenv("DECISION_AUTO_OVERLAY_INTERVAL_MS", "2000").strip() or "2000")
        except Exception:
            self._auto_overlay_interval_ms = 2000

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        await self._load_constraints_from_redis()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._task = None

    async def update_constraints(self, **kwargs) -> None:
        """动态更新约束配置（支持运行时修改）"""
        current = {
            "max_exposure_per_symbol": self._constraints.max_exposure_per_symbol,
            "max_total_exposure": self._constraints.max_total_exposure,
            "min_profit_rate": self._constraints.min_profit_rate,
            "max_positions": self._constraints.max_positions,
            "blacklist_symbols": self._constraints.blacklist_symbols,
            "whitelist_symbols": self._constraints.whitelist_symbols,
            "max_drawdown_per_symbol": self._constraints.max_drawdown_per_symbol,
            "liquidity_score_min": self._constraints.liquidity_score_min,
            "max_spread_rate": self._constraints.max_spread_rate,
            "max_data_age_ms": self._constraints.max_data_age_ms,
            "min_confidence": self._constraints.min_confidence,
            "max_abs_funding_rate": self._constraints.max_abs_funding_rate,
        }

        normalized: dict = {}
        for k, v in kwargs.items():
            if k in {"blacklist_symbols", "whitelist_symbols"}:
                if v is None:
                    normalized[k] = set()
                elif isinstance(v, (set, frozenset)):
                    normalized[k] = set(v)
                else:
                    normalized[k] = set(list(v))
                continue
            if k in {"max_positions", "max_data_age_ms"}:
                normalized[k] = int(v)
                continue
            if isinstance(v, (int, float, str, Decimal)):
                normalized[k] = Decimal(str(v))
            else:
                normalized[k] = v

        current.update(normalized)
        self._constraints = RiskConstraints(**current)
        await self._persist_constraints_to_redis()
        logger.info(f"决策器约束已更新: {self._constraints}")

    async def _persist_constraints_to_redis(self) -> None:
        redis = await get_redis()
        payload = {
            "max_exposure_per_symbol": str(self._constraints.max_exposure_per_symbol),
            "max_total_exposure": str(self._constraints.max_total_exposure),
            "min_profit_rate": str(self._constraints.min_profit_rate),
            "max_positions": self._constraints.max_positions,
            "blacklist_symbols": list(self._constraints.blacklist_symbols),
            "whitelist_symbols": list(self._constraints.whitelist_symbols),
            "max_drawdown_per_symbol": str(self._constraints.max_drawdown_per_symbol),
            "liquidity_score_min": str(self._constraints.liquidity_score_min),
            "max_spread_rate": str(self._constraints.max_spread_rate),
            "max_data_age_ms": self._constraints.max_data_age_ms,
            "min_confidence": str(self._constraints.min_confidence),
            "max_abs_funding_rate": str(self._constraints.max_abs_funding_rate),
        }
        await redis.set(self._constraints_key, json.dumps(payload, ensure_ascii=False))

    async def _load_constraints_from_redis(self) -> None:
        redis = await get_redis()
        raw = await redis.get(self._constraints_key)
        if not raw:
            return
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return
            await self.update_constraints(**data)
        except Exception:
            return

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._scan_and_decide()
            except Exception:
                logger.exception("DecisionService loop error")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.refresh_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _scan_and_decide(self) -> None:
        """扫描机会并应用避险约束，输出决策"""
        start_ts = time.time()
        redis = await get_redis()
        # 读取原始机会
        pipe = redis.pipeline()
        pipe.zrevrange("opportunities:triangular", 0, -1, withscores=True)
        pipe.zrevrange("opportunities:cashcarry", 0, -1, withscores=True)
        tri_raw, cc_raw = await pipe.execute()

        await self._refresh_auto_overlay(tri_raw, cc_raw)
        await self._refresh_strategy_routing()
        candidates: List[Decision] = []

        # 解析三角套利机会
        for member, score in tri_raw:
            try:
                data = json.loads(member)
                if not isinstance(data, dict):
                    continue
                decision = await self._evaluate_triangular(data, Decimal(str(score)))
                if decision:
                    candidates.append(decision)
            except Exception:
                continue

        # 解析期现套利机会
        for member, score in cc_raw:
            try:
                data = json.loads(member)
                if not isinstance(data, dict):
                    continue
                decision = await self._evaluate_cashcarry(data, Decimal(str(score)))
                if decision:
                    candidates.append(decision)
            except Exception:
                continue

        # 应用全局约束并排序
        decisions = self._apply_global_constraints(candidates)

        key = "decisions:latest"
        pipe = redis.pipeline()
        if decisions:
            pipe.delete(key)
            for d in decisions[: self.max_decisions]:
                pipe.zadd(key, {d.to_redis_member(): float(d.risk_score)})  # 用风险评分排序，越小越好
        pipe.expire(key, self.ttl_seconds)
        pipe.set(self._auto_constraints_key, json.dumps(self._auto_overlay, ensure_ascii=False))
        pipe.set(self._effective_constraints_key, json.dumps(self._effective_constraints_snapshot(), ensure_ascii=False))
        await pipe.execute()

        now = time.time()
        elapsed_ms = (now - start_ts) * 1000
        decision_count = len(decisions)
        if (now - self._last_log_ts) >= 10 or self._last_decision_count != decision_count:
            logger.info(f"决策器产出 {decision_count} 条决策 (scan {elapsed_ms:.1f}ms)")
            self._last_log_ts = now
            self._last_decision_count = decision_count

        metrics_key = "metrics:decision_service"
        try:
            pipe = redis.pipeline()
            pipe.hset(metrics_key, mapping={
                "last_scan_ms": f"{elapsed_ms:.1f}",
                "decision_count": str(decision_count),
                "timestamp_ms": str(int(now * 1000)),
            })
            pipe.expire(metrics_key, 120)
            await pipe.execute()
        except Exception:
            pass

    async def _evaluate_triangular(self, data: dict, profit_rate: Decimal) -> Optional[Decision]:
        """评估三角套利机会"""
        symbols = data.get("symbols", [])
        if not symbols or len(symbols) != 3:
            return None

        # 取主要币种（第一个非USDT）作为敞口标的
        main_symbol = next((s for s in symbols if not s.endswith("/USDT")), symbols[0])
        base = main_symbol.split("/")[0]

        # 人为约束检查
        if not self._check_symbol_constraints(base):
            return None
        if profit_rate < self._effective_min_profit_rate():
            return None

        # 估算敞口（假设用 1000 USDT 作为基准）
        estimated_exposure = Decimal('1000')
        if estimated_exposure > self._effective_max_exposure_per_symbol():
            return None

        # 机器人动态风险指标
        confidence = await self._calculate_confidence(symbols, profit_rate)
        if confidence < self._constraints.min_confidence:
            return None

        if not await self._check_market_safety(base):
            return None

        risk_score = await self._calculate_risk_score(base, estimated_exposure, profit_rate)

        return Decision(
            strategy_type="triangular",
            exchange_id=data.get("exchange", self.exchange_id),
            symbol=main_symbol,
            direction="triangular",
            expected_profit_rate=profit_rate,
            estimated_exposure=estimated_exposure,
            risk_score=risk_score,
            confidence=confidence,
            timestamp_ms=int(time.time() * 1000),
            raw_opportunity=data,
        )

    async def _evaluate_cashcarry(self, data: dict, profit_rate: Decimal) -> Optional[Decision]:
        """评估期现套利机会"""
        symbol = data.get("symbol", "")
        if not symbol:
            return None
        base = symbol.split("/")[0]

        if not self._check_symbol_constraints(base):
            return None
        if profit_rate < self._effective_min_profit_rate():
            return None

        estimated_exposure = Decimal('1000')
        if estimated_exposure > self._effective_max_exposure_per_symbol():
            return None

        confidence = await self._calculate_confidence([symbol], profit_rate)
        if confidence < self._constraints.min_confidence:
            return None

        if not await self._check_market_safety(base):
            return None

        if not await self._check_funding_safety(symbol):
            return None

        risk_score = await self._calculate_risk_score(base, estimated_exposure, profit_rate)

        return Decision(
            strategy_type="cashcarry",
            exchange_id=data.get("exchange", self.exchange_id),
            symbol=symbol,
            direction=data.get("direction", "long_spot_short_perp"),
            expected_profit_rate=profit_rate,
            estimated_exposure=estimated_exposure,
            risk_score=risk_score,
            confidence=confidence,
            timestamp_ms=int(time.time() * 1000),
            raw_opportunity=data,
        )

    def _check_symbol_constraints(self, base: str) -> bool:
        """检查币种黑白名单"""
        if base in self._constraints.blacklist_symbols:
            return False
        if base in set(self._auto_overlay.get("blacklist_symbols") or []):
            return False
        if self._constraints.whitelist_symbols and base not in self._constraints.whitelist_symbols:
            return False
        return True

    def _effective_min_profit_rate(self) -> Decimal:
        boost = Decimal(str(self._auto_overlay.get("min_profit_rate_boost") or "0"))
        return self._constraints.min_profit_rate + boost

    def _effective_max_exposure_per_symbol(self) -> Decimal:
        mult = Decimal(str(self._auto_overlay.get("exposure_multiplier") or "1"))
        return (self._constraints.max_exposure_per_symbol * mult).quantize(Decimal('0.01'))

    def _effective_constraints_snapshot(self) -> dict:
        return {
            "regime": self._auto_overlay.get("regime"),
            "max_exposure_per_symbol": str(self._effective_max_exposure_per_symbol()),
            "max_total_exposure": str(self._constraints.max_total_exposure),
            "min_profit_rate": str(self._effective_min_profit_rate()),
            "max_positions": self._constraints.max_positions,
            "blacklist_symbols": sorted(set(self._constraints.blacklist_symbols) | set(self._auto_overlay.get("blacklist_symbols") or [])),
            "whitelist_symbols": sorted(self._constraints.whitelist_symbols),
            "max_drawdown_per_symbol": str(self._constraints.max_drawdown_per_symbol),
            "liquidity_score_min": str(self._constraints.liquidity_score_min),
            "max_spread_rate": str(self._constraints.max_spread_rate),
            "max_data_age_ms": self._constraints.max_data_age_ms,
            "min_confidence": str(self._constraints.min_confidence),
            "max_abs_funding_rate": str(self._constraints.max_abs_funding_rate),
        }

    async def _refresh_auto_overlay(self, tri_raw, cc_raw) -> None:
        now_ms = int(time.time() * 1000)
        if self._auto_overlay.get("timestamp_ms"):
            try:
                last_ts = int(self._auto_overlay.get("timestamp_ms") or 0)
                if (now_ms - last_ts) < self._auto_overlay_interval_ms:
                    return
            except Exception:
                pass
        symbols: list[str] = []
        for member, _ in (tri_raw[:20] if tri_raw else []):
            try:
                data = json.loads(member)
                if isinstance(data, dict):
                    for s in data.get("symbols", [])[:3]:
                        if isinstance(s, str) and s.endswith("/USDT"):
                            symbols.append(s)
            except Exception:
                continue
        for member, _ in (cc_raw[:20] if cc_raw else []):
            try:
                data = json.loads(member)
                if isinstance(data, dict) and isinstance(data.get("symbol"), str):
                    symbols.append(data["symbol"])
            except Exception:
                continue

        symbols = list(dict.fromkeys(symbols))[:30]
        if not symbols:
            self._auto_overlay = {
                "timestamp_ms": now_ms,
                "min_profit_rate_boost": "0",
                "exposure_multiplier": "1",
                "blacklist_symbols": [],
                "regime": "UNKNOWN",
            }
            return

        spreads: list[float] = []
        ages: list[int] = []
        low_liq_bases: set[str] = set()
        semaphore = asyncio.Semaphore(max(1, self._concurrency))

        async def _fetch_metrics(s: str):
            async with semaphore:
                base = s.split("/")[0]
                tob = await self._repo.get_orderbook_tob(self.exchange_id, s)
                age_ms = None
                if tob.timestamp_ms:
                    age_ms = max(0, now_ms - tob.timestamp_ms)
                bba = await self._repo.get_best_bid_ask(self.exchange_id, s, "spot")
                if age_ms is None or age_ms > 60000:
                    bba_ts = bba.timestamp
                    if bba_ts:
                        age_ms = max(0, now_ms - int(bba_ts))

                bid = bba.bid
                ask = bba.ask
                mid = None
                if bid is not None and ask is not None and (bid + ask) > 0:
                    mid = (bid + ask) / 2
                spread = abs(ask - bid) / mid if (mid and ask is not None and bid is not None) else None

                liquidity_low = False
                vol = bba.volume
                if vol is not None:
                    liquidity_score = min(1.0, max(0.0, float(vol) / 100000000.0))
                    if liquidity_score < 0.05:
                        liquidity_low = True

                return base, age_ms, spread, liquidity_low

        results = await asyncio.gather(*[_fetch_metrics(s) for s in symbols], return_exceptions=True)
        for item in results:
            if isinstance(item, Exception):
                continue
            base, age_ms, spread, liquidity_low = item
            if age_ms is not None and age_ms <= 60000:
                ages.append(age_ms)
            if spread is not None:
                spreads.append(spread)
            if liquidity_low:
                low_liq_bases.add(base)

        avg_age = int(sum(ages) / len(ages)) if ages else 0
        avg_spread = float(sum(spreads) / len(spreads)) if spreads else 0.0

        boost = Decimal('0')
        mult = Decimal('1')
        if avg_age > self._constraints.max_data_age_ms:
            boost += self._constraints.min_profit_rate
            mult = Decimal('0.5')
        elif avg_age > int(self._constraints.max_data_age_ms * 0.7):
            boost += (self._constraints.min_profit_rate * Decimal('0.5'))

        if avg_spread > float(self._constraints.max_spread_rate):
            boost += self._constraints.min_profit_rate
            mult = min(mult, Decimal('0.5'))
        elif avg_spread > float(self._constraints.max_spread_rate) * 0.7:
            boost += (self._constraints.min_profit_rate * Decimal('0.5'))

        regime_snapshot = await self._regime_service.refresh(symbols)
        if regime_snapshot.regime == "STRESS":
            boost += self._constraints.min_profit_rate
            mult = min(mult, Decimal('0.3'))
        elif regime_snapshot.regime == "DOWNTREND":
            boost += (self._constraints.min_profit_rate * Decimal('0.5'))
            mult = min(mult, Decimal('0.6'))
        elif regime_snapshot.regime == "UPTREND":
            boost += (self._constraints.min_profit_rate * Decimal('0.2'))
            mult = min(mult, Decimal('0.8'))

        self._auto_overlay = {
            "timestamp_ms": now_ms,
            "min_profit_rate_boost": str(boost),
            "exposure_multiplier": str(mult),
            "blacklist_symbols": sorted(low_liq_bases),
            "avg_data_age_ms": avg_age,
            "avg_spread_rate": avg_spread,
            "regime": regime_snapshot.regime,
            "regime_metrics": regime_snapshot.to_dict(),
        }

    async def _check_market_safety(self, base: str) -> bool:
        symbol = f"{base}/USDT"
        tob = await self._repo.get_orderbook_tob(self.exchange_id, symbol)
        now_ms = int(time.time() * 1000)
        bba = None
        if tob.timestamp_ms and (now_ms - tob.timestamp_ms) > self._constraints.max_data_age_ms:
            bba_ts = None
            try:
                bba = await self._repo.get_best_bid_ask(self.exchange_id, symbol, "spot")
                bba_ts = bba.timestamp
            except Exception:
                bba_ts = None
            if not bba_ts or (now_ms - int(bba_ts)) > self._constraints.max_data_age_ms:
                return False

        if bba is None:
            bba = await self._repo.get_best_bid_ask(self.exchange_id, symbol, "spot")
        bid = bba.bid
        ask = bba.ask
        if bid is not None and ask is not None and (bid + ask) > 0:
            mid = (bid + ask) / 2
            spread_rate = abs(ask - bid) / mid if mid else 1.0
            if Decimal(str(spread_rate)) > self._constraints.max_spread_rate:
                return False

        vol = bba.volume
        if vol is not None:
            liquidity = Decimal(str(vol)) / Decimal('100000000')
            liquidity_score = max(Decimal('0'), min(Decimal('1'), liquidity))
            if liquidity_score < self._constraints.liquidity_score_min:
                return False

        return True

    async def _check_funding_safety(self, symbol: str) -> bool:
        try:
            fr = await self._repo.get_funding(self.exchange_id, symbol)
            rate = fr.rate
            if rate is None:
                return True
            if abs(Decimal(str(rate))) > self._constraints.max_abs_funding_rate:
                return False
            return True
        except Exception:
            return True

    def _apply_global_constraints(self, candidates: List[Decision]) -> List[Decision]:
        """全局约束：去重同币种、控制总敞口、按风险排序"""
        routed = []
        regime = str(self._auto_overlay.get("regime") or "RANGE").upper()
        for d in candidates:
            routing = self._get_routing_for_strategy(d.strategy_type)
            allow_short = routing.get("allow_short", True)
            if not allow_short and "short" in (d.direction or ""):
                continue
            weight = routing.get("regime_weights", {}).get(regime, 1.0)
            try:
                weight_value = float(weight)
            except Exception:
                weight_value = 1.0
            if weight_value <= 0:
                continue
            d.routing_weight = Decimal(str(weight_value))
            d.regime = regime
            try:
                d.risk_score = (d.risk_score / Decimal(str(weight_value))).quantize(Decimal("0.0001"))
            except Exception:
                pass
            routed.append(d)

        # 去重：同一币种只保留风险评分最低的
        best_by_symbol: Dict[str, Decision] = {}
        for d in routed:
            base = d.symbol.split("/")[0]
            if base not in best_by_symbol or d.risk_score < best_by_symbol[base].risk_score:
                best_by_symbol[base] = d

        filtered = list(best_by_symbol.values())

        # 控制总敞口（简单按数量限制，后续可扩展真实资金模型）
        if len(filtered) > self._constraints.max_positions:
            filtered.sort(key=lambda x: x.risk_score)
            filtered = filtered[: self._constraints.max_positions]

        # 按风险评分排序（风险越小越优先）
        filtered.sort(key=lambda x: (x.risk_score, -x.expected_profit_rate))
        return filtered

    async def _refresh_strategy_routing(self) -> None:
        now_ms = int(time.time() * 1000)
        if self._routing_cache and (now_ms - self._routing_cache_ts) < self._routing_cache_ttl_ms:
            return
        try:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                user_id = await conn.fetchval("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")
                if not user_id:
                    return
                rows = await conn.fetch(
                    """
                    SELECT strategy_type, config, is_enabled
                    FROM strategy_configs
                    WHERE user_id = $1
                    """,
                    user_id,
                )
        except Exception:
            return

        routing: dict = {}
        for row in rows:
            cfg = row.get("config") or {}
            if isinstance(cfg, str):
                try:
                    cfg = json.loads(cfg)
                except Exception:
                    cfg = {}
            routing[str(row["strategy_type"])] = {
                "allow_short": bool(cfg.get("allow_short", True)),
                "max_leverage": float(cfg.get("max_leverage", 1.0)),
                "regime_weights": _normalize_regime_weights(cfg.get("regime_weights")),
                "is_enabled": bool(row.get("is_enabled")),
            }
        self._routing_cache = routing
        self._routing_cache_ts = now_ms

    def _get_routing_for_strategy(self, strategy_type: str) -> dict:
        normalized = str(strategy_type or "").lower()
        if normalized == "cashcarry":
            normalized = "funding_rate"
        return self._routing_cache.get(normalized, {
            "allow_short": True,
            "max_leverage": 1.0,
            "regime_weights": _normalize_regime_weights({}),
            "is_enabled": True,
        })


def _normalize_regime_weights(weights: Optional[dict]) -> dict:
    base = {
        "RANGE": 1.0,
        "DOWNTREND": 0.6,
        "UPTREND": 0.7,
        "STRESS": 0.2,
    }
    if not isinstance(weights, dict):
        return base
    for key, value in weights.items():
        if not key:
            continue
        k = str(key).upper()
        try:
            base[k] = float(value)
        except Exception:
            continue
    return base

    async def _calculate_risk_score(self, base: str, exposure: Decimal, profit_rate: Decimal) -> Decimal:
        """动态风险评分（机器人自行定义）"""
        # 简单模型：波动率 + 流动性 + 敞口 + 收益率
        try:
            # 获取最新价作为波动率代理（实际可用历史数据）
            ticker = await self._repo.get_best_bid_ask(self.exchange_id, f"{base}/USDT", "spot")
            mid = ticker.bid or ticker.ask or ticker.last
            if not mid:
                return Decimal('1.0')  # 无数据时给高风险

            # 假设波动率 = bid-ask spread / mid
            spread = ((ticker.ask or 0) - (ticker.bid or 0))
            volatility = spread / mid if mid else Decimal('1')

            # 流动性评分 = volume / 1e8（归一化）
            liquidity = Decimal(str(ticker.volume or 0)) / Decimal('100000000')
            liquidity_score = max(Decimal('0'), min(Decimal('1'), liquidity))

            # 敞口因子
            exposure_factor = exposure / self._constraints.max_exposure_per_symbol

            # 收益因子（收益越高风险越低）
            profit_factor = 1 - profit_rate

            # 综合风险评分（越低越好）
            risk = volatility * Decimal('0.4') + (1 - liquidity_score) * Decimal('0.3') + exposure_factor * Decimal('0.2') + profit_factor * Decimal('0.1')
            return max(Decimal('0'), min(Decimal('1'), risk))
        except Exception:
            return Decimal('1.0')

    async def _calculate_confidence(self, symbols: List[str], profit_rate: Decimal) -> Decimal:
        """置信度：数据新鲜度 + 收益率稳定性"""
        try:
            now_ms = int(time.time() * 1000)
            ages = []
            semaphore = asyncio.Semaphore(max(1, self._concurrency))

            async def _get_age(s: str):
                async with semaphore:
                    tob = await self._repo.get_orderbook_tob(self.exchange_id, s)
                    age_ms = None
                    if tob.timestamp_ms:
                        age_ms = now_ms - tob.timestamp_ms
                    if age_ms is None or age_ms > 60000:
                        try:
                            bba_ts = (await self._repo.get_best_bid_ask(self.exchange_id, s, "spot")).timestamp
                            if bba_ts:
                                age_ms = now_ms - int(bba_ts)
                        except Exception:
                            pass
                    if age_ms is not None and 0 <= age_ms <= 60000:
                        return age_ms
                return None

            results = await asyncio.gather(*[_get_age(s) for s in symbols], return_exceptions=True)
            for item in results:
                if isinstance(item, Exception) or item is None:
                    continue
                ages.append(item)
            if not ages:
                return Decimal('0.5')
            avg_age_ms = sum(ages) / len(ages)
            # 数据越新置信度越高
            freshness = max(Decimal('0'), 1 - Decimal(avg_age_ms) / Decimal('30000'))  # 30秒内算新鲜
            # 收益率越高置信度略高（防止假信号）
            profit_confidence = min(Decimal('1'), profit_rate * Decimal('100'))
            return (freshness * Decimal('0.7') + profit_confidence * Decimal('0.3')).quantize(Decimal('0.01'))
        except Exception:
            return Decimal('0.5')
