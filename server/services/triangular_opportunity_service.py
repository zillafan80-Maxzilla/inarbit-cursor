import asyncio
import json
import logging
import time
import os
from dataclasses import dataclass
from typing import Optional

from ..db import get_pg_pool
from ..db import get_redis
from ..services.config_service import get_config_service
from ..services.market_data_repository import MarketDataRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TriangularOpportunity:
    exchange_id: str
    path: str
    symbols: list[str]
    profit_rate: float
    timestamp_ms: int

    def to_redis_member(self) -> str:
        return json.dumps(
            {
                "strategyType": "triangular",
                "exchange": self.exchange_id,
                "path": self.path,
                "symbols": self.symbols,
                "profitRate": self.profit_rate,
                "timestamp": self.timestamp_ms,
            },
            ensure_ascii=False,
        )


class TriangularOpportunityService:
    def __init__(
        self,
        exchange_id: str = "binance",
        base_currency: str = "USDT",
        min_profit_rate: float = 0.001,
        fee_rate: float = 0.0004,
        refresh_interval_seconds: float = 2.0,
        ttl_seconds: int = 10,
        max_opportunities: int = 50,
    ):
        self.exchange_id = exchange_id
        self.base_currency = base_currency
        self.min_profit_rate = min_profit_rate
        self.fee_rate = fee_rate
        try:
            env_interval = float(os.getenv("TRIANGULAR_REFRESH_INTERVAL", "").strip() or 0)
        except Exception:
            env_interval = 0
        self.refresh_interval_seconds = env_interval if env_interval > 0 else refresh_interval_seconds
        self.ttl_seconds = ttl_seconds
        self.max_opportunities = max_opportunities

        self._repo = MarketDataRepository()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._seed_done = False
        self._last_log_ts: float = 0.0
        self._last_opp_count: Optional[int] = None
        try:
            self._concurrency = int(os.getenv("TRIANGULAR_CONCURRENCY", "50").strip() or "50")
        except Exception:
            self._concurrency = 50

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        if not self._seed_done:
            try:
                await self._ensure_cross_pairs()
            except Exception:
                logger.exception("ensure_cross_pairs failed")
            self._seed_done = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._scan_and_write()
            except Exception:
                logger.exception("TriangularOpportunityService loop error")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.refresh_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _scan_and_write(self) -> None:
        start_ts = time.time()
        config = await get_config_service()
        pairs = await config.get_pairs_for_exchange(self.exchange_id)

        edges = await self._build_edges(pairs)
        opportunities = self._find_triangles(edges)

        redis = await get_redis()
        key = "opportunities:triangular"

        pipe = redis.pipeline()
        pipe.delete(key)

        kept = 0
        for opp in opportunities:
            if opp.profit_rate < self.min_profit_rate:
                continue
            pipe.zadd(key, {opp.to_redis_member(): float(opp.profit_rate)})
            kept += 1
            if kept >= self.max_opportunities:
                break

        pipe.expire(key, self.ttl_seconds)
        await pipe.execute()

        elapsed_ms = (time.time() - start_ts) * 1000
        opp_count = len(opportunities)
        now = time.time()
        if (now - self._last_log_ts) >= 10 or self._last_opp_count != opp_count:
            logger.info(
                f"Triangular 扫描完成: pairs={len(pairs)} opps={opp_count} time={elapsed_ms:.1f}ms"
            )
            self._last_log_ts = now
            self._last_opp_count = opp_count

        metrics_key = "metrics:triangular_service"
        try:
            pipe = redis.pipeline()
            pipe.hset(metrics_key, mapping={
                "last_scan_ms": f"{elapsed_ms:.1f}",
                "pairs": str(len(pairs)),
                "opportunities": str(opp_count),
                "timestamp_ms": str(int(now * 1000)),
            })
            pipe.expire(metrics_key, 120)
            await pipe.execute()
        except Exception:
            pass

    async def _ensure_cross_pairs(self) -> None:
        if self.exchange_id != "binance":
            return

        needed = [
            ("ETH/BTC", "ETH", "BTC"),
            ("SOL/BTC", "SOL", "BTC"),
            ("BNB/BTC", "BNB", "BTC"),
            ("XRP/BTC", "XRP", "BTC"),
            ("DOGE/BTC", "DOGE", "BTC"),
            ("ADA/BTC", "ADA", "BTC"),
        ]

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            inserted_any = False
            for symbol, base, quote in needed:
                await conn.execute(
                    """
                    INSERT INTO trading_pairs (symbol, base_currency, quote_currency, is_active, supported_exchanges)
                    VALUES ($1, $2, $3, true, ARRAY[$4])
                    ON CONFLICT (symbol) DO UPDATE
                    SET is_active = true,
                        supported_exchanges = CASE
                            WHEN $4 = ANY(trading_pairs.supported_exchanges) THEN trading_pairs.supported_exchanges
                            ELSE array_append(trading_pairs.supported_exchanges, $4)
                        END
                    """,
                    symbol,
                    base,
                    quote,
                    self.exchange_id,
                )
                inserted_any = True

        if inserted_any:
            config = await get_config_service()
            await config.refresh_cache()

    async def _build_edges(self, pairs) -> dict[str, dict[str, dict]]:
        """
        edges[u][v] = {
          "symbol": "BASE/QUOTE",
          "action": "buy"|"sell",
          "rate": float,
        }
        rate 含义：u -> v 的单位兑换比例（忽略手续费）
        """
        edges: dict[str, dict[str, dict]] = {}
        semaphore = asyncio.Semaphore(max(1, self._concurrency))

        async def _fetch_tob(pair):
            async with semaphore:
                tob = await self._repo.get_orderbook_tob(self.exchange_id, pair.symbol)
                return pair, tob

        results = await asyncio.gather(*[_fetch_tob(p) for p in pairs], return_exceptions=True)

        for item in results:
            if isinstance(item, Exception):
                continue
            p, tob = item
            symbol = p.symbol

            base = p.base
            quote = p.quote

            edges.setdefault(base, {})
            edges.setdefault(quote, {})

            if tob.best_bid_price and tob.best_bid_price > 0:
                # base -> quote: 卖出 base，得到 quote
                edges[base][quote] = {
                    "symbol": symbol,
                    "action": "sell",
                    "rate": float(tob.best_bid_price),
                }

            if tob.best_ask_price and tob.best_ask_price > 0:
                # quote -> base: 用 quote 买入 base
                edges[quote][base] = {
                    "symbol": symbol,
                    "action": "buy",
                    "rate": 1.0 / float(tob.best_ask_price),
                }

        return edges

    def _find_triangles(self, edges: dict[str, dict[str, dict]]) -> list[TriangularOpportunity]:
        base = self.base_currency
        if base not in edges:
            return []

        now_ms = int(time.time() * 1000)
        opps: list[TriangularOpportunity] = []

        fee_mul = (1 - self.fee_rate) ** 3

        for c1, e1 in edges[base].items():
            for c2, e2 in edges.get(c1, {}).items():
                if c2 == base:
                    continue
                e3 = edges.get(c2, {}).get(base)
                if not e3:
                    continue

                rate = float(e1["rate"]) * float(e2["rate"]) * float(e3["rate"]) * fee_mul
                profit_rate = rate - 1.0

                path = f"{base} -> {c1} -> {c2} -> {base}"
                symbols = [e1["symbol"], e2["symbol"], e3["symbol"]]

                opps.append(
                    TriangularOpportunity(
                        exchange_id=self.exchange_id,
                        path=path,
                        symbols=symbols,
                        profit_rate=profit_rate,
                        timestamp_ms=now_ms,
                    )
                )

        opps.sort(key=lambda x: x.profit_rate, reverse=True)
        return opps
