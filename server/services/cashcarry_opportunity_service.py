import asyncio
import json
import logging
import time
import os
from dataclasses import dataclass
from typing import Optional

from ..db import get_redis
from ..services.config_service import get_config_service
from ..services.market_data_repository import MarketDataRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CashCarryOpportunity:
    exchange_id: str
    symbol: str
    direction: str
    spot_price: float
    perp_price: float
    basis_rate: float
    funding_rate: float
    profit_rate: float
    timestamp_ms: int

    def to_redis_member(self) -> str:
        spot_ask = self.spot_price if self.direction == "long_spot_short_perp" else None
        perp_bid = self.perp_price if self.direction == "long_spot_short_perp" else None
        spot_bid = self.spot_price if self.direction == "short_spot_long_perp" else None
        perp_ask = self.perp_price if self.direction == "short_spot_long_perp" else None
        return json.dumps(
            {
                "strategyType": "cashcarry",
                "exchange": self.exchange_id,
                "symbol": self.symbol,
                "direction": self.direction,
                "spotAsk": spot_ask,
                "perpBid": perp_bid,
                "spotBid": spot_bid,
                "perpAsk": perp_ask,
                "spotPrice": self.spot_price,
                "perpPrice": self.perp_price,
                "basisRate": self.basis_rate,
                "fundingRate": self.funding_rate,
                "profitRate": self.profit_rate,
                "timestamp": self.timestamp_ms,
            },
            ensure_ascii=False,
        )


class CashCarryOpportunityService:
    def __init__(
        self,
        exchange_id: str = "binance",
        quote_currency: str = "USDT",
        min_profit_rate: float = 0.001,
        spot_fee_rate: float = 0.0004,
        perp_fee_rate: float = 0.0004,
        funding_horizon_intervals: int = 3,
        refresh_interval_seconds: float = 2.0,
        ttl_seconds: int = 10,
        max_opportunities: int = 50,
    ):
        self.exchange_id = exchange_id
        self.quote_currency = quote_currency
        self.min_profit_rate = min_profit_rate
        self.spot_fee_rate = spot_fee_rate
        self.perp_fee_rate = perp_fee_rate
        self.funding_horizon_intervals = funding_horizon_intervals
        try:
            env_interval = float(os.getenv("CASHCARRY_REFRESH_INTERVAL", "").strip() or 0)
        except Exception:
            env_interval = 0
        self.refresh_interval_seconds = env_interval if env_interval > 0 else refresh_interval_seconds
        self.ttl_seconds = ttl_seconds
        self.max_opportunities = max_opportunities

        self._repo = MarketDataRepository()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._last_log_ts: float = 0.0
        self._last_opp_count: Optional[int] = None
        try:
            self._concurrency = int(os.getenv("CASHCARRY_CONCURRENCY", "50").strip() or "50")
        except Exception:
            self._concurrency = 50

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
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
                logger.exception("CashCarryOpportunityService loop error")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.refresh_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _collect_symbols_from_set(
        self,
        redis,
        key: str,
        limit: int = 200,
    ) -> list[str]:
        symbols: list[str] = []
        cursor = 0
        while True:
            cursor, members = await redis.sscan(cursor=cursor, name=key, count=200)
            for m in members or []:
                sym = m.decode() if isinstance(m, (bytes, bytearray)) else str(m)
                if not sym.endswith(f"/{self.quote_currency}"):
                    continue
                symbols.append(sym)
                if len(symbols) >= limit:
                    return symbols
            if cursor == 0:
                break
        return symbols

    async def _fetch_symbol_data(self, symbol: str, semaphore: asyncio.Semaphore):
        async with semaphore:
            spot_task = self._repo.get_best_bid_ask(self.exchange_id, symbol, account_type="spot")
            perp_task = self._repo.get_best_bid_ask(self.exchange_id, symbol, account_type="perp")
            funding_task = self._repo.get_funding(self.exchange_id, symbol)
            tob_task = self._repo.get_orderbook_tob(self.exchange_id, symbol)
            spot, perp, funding, tob = await asyncio.gather(
                spot_task,
                perp_task,
                funding_task,
                tob_task,
                return_exceptions=False,
            )
            return symbol, spot, perp, funding, tob

    async def _scan_and_write(self) -> None:
        start_ts = time.time()
        config = await get_config_service()
        pairs = await config.get_pairs_for_exchange(self.exchange_id)

        candidates = [p for p in pairs if p.quote == self.quote_currency]
        symbols: list[str] = [p.symbol for p in candidates]

        if len(symbols) < 50:
            redis = await get_redis()
            seen = set(symbols)
            indexed = await self._collect_symbols_from_set(
                redis,
                key=f"symbols:funding:{self.exchange_id}",
                limit=200,
            )
            if not indexed:
                pattern = f"funding:{self.exchange_id}:*"
                cursor = 0
                while True:
                    cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=200)
                    for k in keys or []:
                        kk = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
                        parts = kk.split(":", 2)
                        if len(parts) < 3:
                            continue
                        sym = parts[2]
                        if not sym.endswith(f"/{self.quote_currency}"):
                            continue
                        indexed.append(sym)
                        if len(indexed) >= 200:
                            break
                    if cursor == 0 or len(indexed) >= 200:
                        break
            for sym in indexed:
                if sym in seen:
                    continue
                symbols.append(sym)
                seen.add(sym)
                if len(symbols) >= 200:
                    break

        if len(symbols) < 50:
            redis = await get_redis()
            seen = set(symbols)
            indexed = await self._collect_symbols_from_set(
                redis,
                key=f"symbols:ticker_futures:{self.exchange_id}",
                limit=200,
            )
            if not indexed:
                pattern = f"ticker_futures:{self.exchange_id}:*"
                cursor = 0
                while True:
                    cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=200)
                    for k in keys or []:
                        kk = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
                        parts = kk.split(":", 2)
                        if len(parts) < 3:
                            continue
                        sym = parts[2]
                        if not sym.endswith(f"/{self.quote_currency}"):
                            continue
                        indexed.append(sym)
                        if len(indexed) >= 200:
                            break
                    if cursor == 0 or len(indexed) >= 200:
                        break
            for sym in indexed:
                if sym in seen:
                    continue
                symbols.append(sym)
                seen.add(sym)
                if len(symbols) >= 200:
                    break

        now_ms = int(time.time() * 1000)
        opps: list[CashCarryOpportunity] = []

        semaphore = asyncio.Semaphore(max(1, self._concurrency))
        results = await asyncio.gather(
            *[self._fetch_symbol_data(symbol, semaphore) for symbol in symbols],
            return_exceptions=True,
        )

        for item in results:
            if isinstance(item, Exception):
                continue
            symbol, spot, perp, funding, tob = item

            spot_bid = tob.best_bid_price if tob.best_bid_price is not None else (spot.bid if spot.bid is not None else spot.last)
            spot_ask = tob.best_ask_price if tob.best_ask_price is not None else (spot.ask if spot.ask is not None else spot.last)
            perp_bid = perp.bid if perp.bid is not None else perp.last
            perp_ask = perp.ask if perp.ask is not None else perp.last

            funding_rate = float(funding.rate or 0.0) * float(self.funding_horizon_intervals)
            fee_cost = self.spot_fee_rate + self.perp_fee_rate

            # cash&carry: 买现货(ask) + 卖永续(bid)，若 funding>0 则 short 收益
            if spot_ask is not None and perp_bid is not None and float(spot_ask) != 0:
                basis_rate = (float(perp_bid) - float(spot_ask)) / float(spot_ask)
                if abs(float(basis_rate)) <= 0.1:
                    profit_rate = basis_rate + funding_rate - fee_cost
                    if profit_rate >= self.min_profit_rate:
                        opps.append(
                            CashCarryOpportunity(
                                exchange_id=self.exchange_id,
                                symbol=symbol,
                                direction="long_spot_short_perp",
                                spot_price=float(spot_ask),
                                perp_price=float(perp_bid),
                                basis_rate=float(basis_rate),
                                funding_rate=float(funding_rate),
                                profit_rate=float(profit_rate),
                                timestamp_ms=now_ms,
                            )
                        )

            # reverse cash&carry: 卖现货(bid) + 买永续(ask)，若 funding<0 则 long 收益
            if spot_bid is not None and perp_ask is not None and float(spot_bid) != 0:
                basis_rate = (float(perp_ask) - float(spot_bid)) / float(spot_bid)
                if abs(float(basis_rate)) <= 0.1:
                    profit_rate = (-basis_rate) + (-funding_rate) - fee_cost
                    if profit_rate >= self.min_profit_rate:
                        opps.append(
                            CashCarryOpportunity(
                                exchange_id=self.exchange_id,
                                symbol=symbol,
                                direction="short_spot_long_perp",
                                spot_price=float(spot_bid),
                                perp_price=float(perp_ask),
                                basis_rate=float(basis_rate),
                                funding_rate=float(funding_rate),
                                profit_rate=float(profit_rate),
                                timestamp_ms=now_ms,
                            )
                        )

        opps.sort(key=lambda x: x.profit_rate, reverse=True)

        redis = await get_redis()
        key = "opportunities:cashcarry"
        pipe = redis.pipeline()
        if opps:
            pipe.delete(key)
            for opp in opps[: self.max_opportunities]:
                pipe.zadd(key, {opp.to_redis_member(): float(opp.profit_rate)})
        pipe.expire(key, self.ttl_seconds)
        await pipe.execute()

        elapsed_ms = (time.time() - start_ts) * 1000
        opp_count = len(opps)
        now = time.time()
        if (now - self._last_log_ts) >= 10 or self._last_opp_count != opp_count:
            logger.info(
                f"CashCarry 扫描完成: symbols={len(symbols)} opps={opp_count} time={elapsed_ms:.1f}ms"
            )
            self._last_log_ts = now
            self._last_opp_count = opp_count

        metrics_key = "metrics:cashcarry_service"
        try:
            pipe = redis.pipeline()
            pipe.hset(metrics_key, mapping={
                "last_scan_ms": f"{elapsed_ms:.1f}",
                "symbols": str(len(symbols)),
                "opportunities": str(opp_count),
                "timestamp_ms": str(int(now * 1000)),
            })
            pipe.expire(metrics_key, 120)
            await pipe.execute()
        except Exception:
            pass
