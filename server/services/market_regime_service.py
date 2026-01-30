import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Iterable

from ..db import get_redis
from .market_data_repository import MarketDataRepository
from .config_service import get_config_service

logger = logging.getLogger(__name__)


@dataclass
class MarketRegimeSnapshot:
    regime: str
    timestamp_ms: int
    avg_return: float
    volatility: float
    avg_spread_rate: float
    avg_volume: float
    avg_data_age_ms: int
    sample_count: int
    symbols: list[str]

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "timestamp_ms": self.timestamp_ms,
            "avg_return": self.avg_return,
            "volatility": self.volatility,
            "avg_spread_rate": self.avg_spread_rate,
            "avg_volume": self.avg_volume,
            "avg_data_age_ms": self.avg_data_age_ms,
            "sample_count": self.sample_count,
            "symbols": self.symbols,
        }


class MarketRegimeService:
    def __init__(self, exchange_id: str = "binance"):
        self.exchange_id = exchange_id
        self._repo = MarketDataRepository()
        self._history: dict[str, deque[float]] = {}
        self._last_refresh_ms = 0
        self._last_snapshot: Optional[MarketRegimeSnapshot] = None
        try:
            self._window_size = int(os.getenv("MARKET_REGIME_WINDOW", "60").strip() or "60")
        except Exception:
            self._window_size = 60
        try:
            self._min_interval_ms = int(os.getenv("MARKET_REGIME_SAMPLE_INTERVAL_MS", "2000").strip() or "2000")
        except Exception:
            self._min_interval_ms = 2000
        try:
            self._min_points = int(os.getenv("MARKET_REGIME_MIN_POINTS", "5").strip() or "5")
        except Exception:
            self._min_points = 5
        try:
            self._trend_threshold = float(os.getenv("MARKET_REGIME_TREND_THRESHOLD", "0.01").strip() or "0.01")
        except Exception:
            self._trend_threshold = 0.01
        try:
            self._vol_high = float(os.getenv("MARKET_REGIME_VOL_HIGH", "0.008").strip() or "0.008")
        except Exception:
            self._vol_high = 0.008
        try:
            self._vol_stress = float(os.getenv("MARKET_REGIME_VOL_STRESS", "0.02").strip() or "0.02")
        except Exception:
            self._vol_stress = 0.02
        try:
            self._spread_stress = float(os.getenv("MARKET_REGIME_SPREAD_STRESS", "0.004").strip() or "0.004")
        except Exception:
            self._spread_stress = 0.004
        try:
            self._max_data_age_ms = int(os.getenv("MARKET_REGIME_MAX_DATA_AGE_MS", "15000").strip() or "15000")
        except Exception:
            self._max_data_age_ms = 15000
        try:
            self._max_symbols = int(os.getenv("MARKET_REGIME_SYMBOL_LIMIT", "8").strip() or "8")
        except Exception:
            self._max_symbols = 8

    async def refresh(self, symbols: Optional[Iterable[str]] = None) -> MarketRegimeSnapshot:
        now_ms = int(time.time() * 1000)
        if self._last_snapshot and (now_ms - self._last_refresh_ms) < self._min_interval_ms:
            return self._last_snapshot

        resolved = await self._resolve_symbols(symbols)
        if not resolved:
            snapshot = MarketRegimeSnapshot(
                regime="UNKNOWN",
                timestamp_ms=now_ms,
                avg_return=0.0,
                volatility=0.0,
                avg_spread_rate=0.0,
                avg_volume=0.0,
                avg_data_age_ms=0,
                sample_count=0,
                symbols=[],
            )
            self._last_snapshot = snapshot
            self._last_refresh_ms = now_ms
            return snapshot

        semaphore = asyncio.Semaphore(40)
        spreads: list[float] = []
        volumes: list[float] = []
        ages: list[int] = []

        async def _fetch(symbol: str):
            async with semaphore:
                bba = await self._repo.get_best_bid_ask(self.exchange_id, symbol, "spot")
                bid = bba.bid
                ask = bba.ask
                last = bba.last
                mid = None
                if bid is not None and ask is not None and (bid + ask) > 0:
                    mid = (bid + ask) / 2.0
                elif last is not None:
                    mid = last
                ts = bba.timestamp
                volume = bba.volume
                spread_rate = None
                if bid is not None and ask is not None and mid:
                    spread_rate = abs(ask - bid) / mid
                return symbol, mid, ts, spread_rate, volume

        results = await asyncio.gather(*[_fetch(s) for s in resolved], return_exceptions=True)
        for item in results:
            if isinstance(item, Exception):
                continue
            symbol, mid, ts, spread_rate, volume = item
            if mid is None or mid <= 0:
                continue
            self._append_history(symbol, float(mid))
            if spread_rate is not None:
                spreads.append(float(spread_rate))
            if volume is not None:
                volumes.append(float(volume))
            if ts:
                ages.append(max(0, now_ms - int(ts)))

        avg_spread = sum(spreads) / len(spreads) if spreads else 0.0
        avg_volume = sum(volumes) / len(volumes) if volumes else 0.0
        avg_age = int(sum(ages) / len(ages)) if ages else 0

        avg_return, volatility = self._calc_return_and_volatility()
        regime = self._classify_regime(avg_return, volatility, avg_spread, avg_age)

        snapshot = MarketRegimeSnapshot(
            regime=regime,
            timestamp_ms=now_ms,
            avg_return=avg_return,
            volatility=volatility,
            avg_spread_rate=avg_spread,
            avg_volume=avg_volume,
            avg_data_age_ms=avg_age,
            sample_count=len(results),
            symbols=resolved,
        )
        self._last_snapshot = snapshot
        self._last_refresh_ms = now_ms

        try:
            redis = await get_redis()
            await redis.hset("metrics:market_regime", mapping=snapshot.to_dict())
            await redis.expire("metrics:market_regime", 120)
        except Exception:
            pass

        return snapshot

    async def _resolve_symbols(self, symbols: Optional[Iterable[str]]) -> list[str]:
        resolved: list[str] = []
        if symbols:
            resolved = [s for s in symbols if isinstance(s, str) and s]
        if not resolved:
            env_symbols = os.getenv("MARKET_REGIME_SYMBOLS", "")
            if env_symbols.strip():
                resolved = [s.strip() for s in env_symbols.split(",") if s.strip()]
        if not resolved:
            try:
                service = await get_config_service()
                pairs = await service.get_pairs_for_exchange(self.exchange_id)
                resolved = [p.symbol for p in pairs if p.symbol.endswith("/USDT")]
            except Exception:
                resolved = []
        if not resolved:
            resolved = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
        return resolved[: self._max_symbols]

    def _append_history(self, symbol: str, price: float) -> None:
        history = self._history.get(symbol)
        if not history:
            history = deque(maxlen=self._window_size)
            self._history[symbol] = history
        history.append(price)

    def _calc_return_and_volatility(self) -> tuple[float, float]:
        returns: list[float] = []
        for prices in self._history.values():
            if len(prices) < self._min_points:
                continue
            first = prices[0]
            last = prices[-1]
            if first > 0:
                returns.append((last - first) / first)
        avg_return = sum(returns) / len(returns) if returns else 0.0

        vol_samples: list[float] = []
        for prices in self._history.values():
            if len(prices) < self._min_points:
                continue
            prev = prices[0]
            for price in list(prices)[1:]:
                if prev > 0 and price > 0:
                    vol_samples.append((price - prev) / prev)
                prev = price
        volatility = _std(vol_samples) if vol_samples else 0.0
        return avg_return, volatility

    def _classify_regime(self, avg_return: float, volatility: float, avg_spread: float, avg_age: int) -> str:
        if avg_age > self._max_data_age_ms or avg_spread > self._spread_stress:
            return "STRESS"
        if volatility >= self._vol_stress:
            return "STRESS"
        if abs(avg_return) >= self._trend_threshold and volatility >= self._vol_high:
            return "UPTREND" if avg_return > 0 else "DOWNTREND"
        return "RANGE"


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance ** 0.5
