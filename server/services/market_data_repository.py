import logging
import time
import os
from dataclasses import dataclass
from typing import Optional

from ..db import get_redis

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BestBidAsk:
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    volume: Optional[float]
    timestamp: Optional[int]


@dataclass(frozen=True)
class OrderBookTOB:
    best_bid_price: Optional[float]
    best_bid_amount: Optional[float]
    best_ask_price: Optional[float]
    best_ask_amount: Optional[float]
    timestamp_ms: Optional[int]


@dataclass(frozen=True)
class FundingInfo:
    rate: Optional[float]
    next_time: Optional[int]
    timestamp: Optional[int]
    mark: Optional[float]
    index: Optional[float]


class MarketDataRepository:
    def __init__(self):
        self._bba_cache: dict[tuple[str, str, str], tuple[int, BestBidAsk]] = {}
        self._tob_cache: dict[tuple[str, str], tuple[int, OrderBookTOB]] = {}
        self._funding_cache: dict[tuple[str, str], tuple[int, FundingInfo]] = {}
        try:
            self._cache_ttl_ms = int(os.getenv("MARKETDATA_CACHE_TTL_MS", "500").strip() or "500")
        except Exception:
            self._cache_ttl_ms = 500
        try:
            self._max_cache_items = int(os.getenv("MARKETDATA_CACHE_MAX_ITEMS", "2000").strip() or "2000")
        except Exception:
            self._max_cache_items = 2000

    async def get_best_bid_ask(self, exchange_id: str, symbol: str, account_type: str = "spot") -> BestBidAsk:
        cache_key = (exchange_id, symbol, account_type)
        now_ms = int(time.time() * 1000)
        cached = self._bba_cache.get(cache_key)
        if cached and (now_ms - cached[0]) <= self._cache_ttl_ms:
            return cached[1]

        redis = await get_redis()
        if account_type == "perp":
            key = f"ticker_futures:{exchange_id}:{symbol}"
            fr_key = f"funding:{exchange_id}:{symbol}"
            pipe = redis.pipeline()
            pipe.hgetall(key)
            pipe.hgetall(fr_key)
            data, fr_data = await pipe.execute()
            data = _normalize_redis_hash(data)
        else:
            key = f"ticker:{exchange_id}:{symbol}"
            data = _normalize_redis_hash(await redis.hgetall(key))

        bid = _parse_float(data.get("bid"))
        ask = _parse_float(data.get("ask"))
        last = _parse_float(data.get("last"))
        volume = _parse_float(data.get("volume"))
        ts = _parse_int(data.get("timestamp"))

        if account_type == "perp" and bid is None and ask is None and last is None:
            fr = _normalize_redis_hash(fr_data) if 'fr_data' in locals() else {}
            mark = _parse_float(fr.get("mark"))
            index = _parse_float(fr.get("index"))
            ts = _parse_int(fr.get("timestamp"))
            ref = mark if mark is not None else index
            if ref is not None:
                bid = ref
                ask = ref
                last = ref

        result = BestBidAsk(
            bid=bid,
            ask=ask,
            last=last,
            volume=volume,
            timestamp=ts,
        )
        if len(self._bba_cache) >= self._max_cache_items:
            self._bba_cache.clear()
        self._bba_cache[cache_key] = (now_ms, result)
        return result

    async def get_orderbook_tob(self, exchange_id: str, symbol: str) -> OrderBookTOB:
        cache_key = (exchange_id, symbol)
        now_ms = int(time.time() * 1000)
        cached = self._tob_cache.get(cache_key)
        if cached and (now_ms - cached[0]) <= self._cache_ttl_ms:
            return cached[1]

        redis = await get_redis()

        bids_key = f"orderbook:{exchange_id}:{symbol}:bids"
        asks_key = f"orderbook:{exchange_id}:{symbol}:asks"
        ts_key = f"orderbook:{exchange_id}:{symbol}:ts"

        pipe = redis.pipeline()
        pipe.zrevrange(bids_key, 0, 0)
        pipe.zrange(asks_key, 0, 0)
        pipe.get(ts_key)
        bid_members, ask_members, ts = await pipe.execute()

        best_bid_price, best_bid_amount = _parse_price_amount(bid_members[0]) if bid_members else (None, None)
        best_ask_price, best_ask_amount = _parse_price_amount(ask_members[0]) if ask_members else (None, None)

        if best_bid_price is None and best_ask_price is None:
            ticker_key = f"ticker:{exchange_id}:{symbol}"
            t = _normalize_redis_hash(await redis.hgetall(ticker_key))
            best_bid_price = _parse_float(t.get("bid"))
            best_ask_price = _parse_float(t.get("ask"))
            if ts is None:
                ts = t.get("timestamp")

        result = OrderBookTOB(
            best_bid_price=best_bid_price,
            best_bid_amount=best_bid_amount,
            best_ask_price=best_ask_price,
            best_ask_amount=best_ask_amount,
            timestamp_ms=_parse_int(ts),
        )
        if len(self._tob_cache) >= self._max_cache_items:
            self._tob_cache.clear()
        self._tob_cache[cache_key] = (now_ms, result)
        return result

    async def get_funding(self, exchange_id: str, symbol: str) -> FundingInfo:
        cache_key = (exchange_id, symbol)
        now_ms = int(time.time() * 1000)
        cached = self._funding_cache.get(cache_key)
        if cached and (now_ms - cached[0]) <= self._cache_ttl_ms:
            return cached[1]

        redis = await get_redis()
        key = f"funding:{exchange_id}:{symbol}"
        data = _normalize_redis_hash(await redis.hgetall(key))

        result = FundingInfo(
            rate=_parse_float(data.get("rate")),
            next_time=_parse_int(data.get("next_time")),
            timestamp=_parse_int(data.get("timestamp")),
            mark=_parse_float(data.get("mark")),
            index=_parse_float(data.get("index")),
        )
        if len(self._funding_cache) >= self._max_cache_items:
            self._funding_cache.clear()
        self._funding_cache[cache_key] = (now_ms, result)
        return result


def _parse_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def _parse_int(v) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    try:
        return int(float(v))
    except Exception:
        return None


def _parse_price_amount(member) -> tuple[Optional[float], Optional[float]]:
    if member is None:
        return None, None
    if isinstance(member, (bytes, bytearray)):
        member = member.decode("utf-8")
    if not isinstance(member, str):
        return None, None

    parts = member.split(":", 1)
    if len(parts) != 2:
        return None, None

    return _parse_float(parts[0]), _parse_float(parts[1])


def _normalize_redis_hash(data: dict) -> dict[str, object]:
    if not data:
        return {}

    out: dict[str, object] = {}
    for k, v in data.items():
        if isinstance(k, (bytes, bytearray)):
            k = k.decode("utf-8")
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("utf-8")
        if isinstance(k, str):
            out[k] = v
    return out
