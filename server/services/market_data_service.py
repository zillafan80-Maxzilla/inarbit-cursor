import asyncio
import logging
import os
import time
from typing import Optional

import aiohttp
from aiohttp.resolver import ThreadedResolver
import ccxt.async_support as ccxt

from ..db import get_pg_pool, get_redis
from ..exchange.binance_connector import apply_binance_base_url, get_binance_base_url
from .config_service import DEFAULT_PAIRS, get_config_service

logger = logging.getLogger(__name__)

_SPOT_TICKER_TTL_SECONDS = 20
_ORDERBOOK_TTL_SECONDS = 15
_FUTURES_TICKER_TTL_SECONDS = 20
_FUNDING_TTL_SECONDS = 60 * 60 * 8

try:
    _MAX_TICKER_SYMBOLS = int(os.getenv("MARKETDATA_MAX_TICKER_SYMBOLS", "200").strip() or "200")
except Exception:
    _MAX_TICKER_SYMBOLS = 200
_EXPAND_USDT_MARKETS = (os.getenv("MARKETDATA_EXPAND_USDT_MARKETS", "0").strip().lower() in {"1", "true", "yes", "y"})
try:
    _MAX_ORDERBOOK_SYMBOLS = int(os.getenv("MARKETDATA_MAX_ORDERBOOK_SYMBOLS", "5").strip() or "5")
except Exception:
    _MAX_ORDERBOOK_SYMBOLS = 5
try:
    _MAX_FUTURES_TICKER_SYMBOLS = int(os.getenv("MARKETDATA_MAX_FUTURES_SYMBOLS", "120").strip() or "120")
except Exception:
    _MAX_FUTURES_TICKER_SYMBOLS = 120
try:
    _MAX_FUNDING_SYMBOLS = int(os.getenv("MARKETDATA_MAX_FUNDING_SYMBOLS", "80").strip() or "80")
except Exception:
    _MAX_FUNDING_SYMBOLS = 80
try:
    _ORDERBOOK_LIMIT = int(os.getenv("MARKETDATA_ORDERBOOK_LIMIT", "10").strip() or "10")
except Exception:
    _ORDERBOOK_LIMIT = 10
try:
    _FETCH_CONCURRENCY = int(os.getenv("MARKETDATA_FETCH_CONCURRENCY", "10").strip() or "10")
except Exception:
    _FETCH_CONCURRENCY = 10
if _FETCH_CONCURRENCY < 1:
    _FETCH_CONCURRENCY = 1
_RETRY_DELAY_SECONDS = 10


class MarketDataService:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._last_metrics_ts: float = 0.0
        try:
            self._poll_interval_seconds = float(os.getenv("MARKETDATA_POLL_INTERVAL", "1").strip() or "1")
        except Exception:
            self._poll_interval_seconds = 1.0

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
            except BaseException:
                pass
            self._task = None

    async def _run(self) -> None:
        use_pro = _should_use_ccxt_pro()
        if use_pro:
            await self._run_ccxt_pro()
            return

        await self._run_polling()

    async def _run_polling(self) -> None:
        # 支持通过环境变量切换交易所
        exchange_provider = os.getenv("EXCHANGE_PROVIDER", "binance").lower()
        logger.info(f"MarketDataService using exchange: {exchange_provider}")
        
        while not self._stop_event.is_set():
            spot = None
            futures = None
            spot_session = None
            futures_session = None
            try:
                if exchange_provider == "okx":
                    spot = ccxt.okx({
                        "apiKey": os.getenv("OKX_API_KEY"),
                        "secret": os.getenv("OKX_API_SECRET"),
                        "password": os.getenv("OKX_PASSPHRASE"),
                        "enableRateLimit": True,
                        "options": {"defaultType": "spot"},
                    })
                    futures = ccxt.okx({
                        "apiKey": os.getenv("OKX_API_KEY"),
                        "secret": os.getenv("OKX_API_SECRET"),
                        "password": os.getenv("OKX_PASSPHRASE"),
                        "enableRateLimit": True,
                        "options": {"defaultType": "swap"},
                    })
                else:
                    spot = ccxt.binance({
                        "enableRateLimit": True,
                        "options": {
                            "defaultType": "spot",
                            # 避免调用受限的 SAPI 接口导致 404
                            "fetchCurrencies": False,
                            "fetchMargins": False,
                        },
                    })

                    futures = ccxt.binance({
                        "enableRateLimit": True,
                        "options": {
                            "defaultType": "future",
                            # 避免调用受限的 SAPI 接口导致 404
                            "fetchCurrencies": False,
                            "fetchMargins": False,
                        },
                    })

                # 自动选择可用 API 地址（适配网络环境，仅 Binance 需要）
                if exchange_provider == "binance":
                    base_url = await get_binance_base_url()
                    apply_binance_base_url(spot, base_url)
                    apply_binance_base_url(futures, base_url)

                spot_session = _create_threaded_dns_session()
                futures_session = _create_threaded_dns_session()
                spot.session = spot_session
                futures.session = futures_session

                spot_markets_ok = True
                futures_markets_ok = True
                try:
                    await spot.load_markets()
                except Exception as e:
                    spot_markets_ok = False
                    logger.warning(f"MarketDataService spot load_markets failed, continue without markets: {e}")
                try:
                    await futures.load_markets()
                except Exception as e:
                    futures_markets_ok = False
                    logger.warning(f"MarketDataService futures load_markets failed, continue without markets: {e}")

                while not self._stop_event.is_set():
                    start_ts = time.time()
                    spot_symbol_count = 0
                    futures_symbol_count = 0
                    funding_symbol_count = 0
                    try:
                        config_spot_symbols = await self._get_symbols_for_exchange(exchange_provider, limit=_MAX_TICKER_SYMBOLS)
                        spot_ticker_symbols = list(config_spot_symbols)
                        if spot_ticker_symbols:
                            spot_symbol_count = len(spot_ticker_symbols)
                            markets = getattr(spot, "markets", None) or {}
                            if markets and _EXPAND_USDT_MARKETS:
                                market_usdt = [s for s in markets.keys() if s.endswith("/USDT")]
                                market_usdt.sort()
                                spot_ticker_symbols = self._merge_symbol_priority(
                                    config_spot_symbols,
                                    market_usdt,
                                    _MAX_TICKER_SYMBOLS,
                                )
                                spot_symbol_count = len(spot_ticker_symbols)

                            tickers = {}
                            try:
                                tickers = await spot.fetch_tickers(spot_ticker_symbols)
                            except Exception:
                                # 批量失败时降级为并发拉取，避免单个 BadSymbol 打断整轮
                                semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

                                async def _fetch_one(sym: str):
                                    async with semaphore:
                                        try:
                                            return sym, await spot.fetch_ticker(sym)
                                        except Exception:
                                            return sym, None

                                results = await asyncio.gather(
                                    *[_fetch_one(s) for s in spot_ticker_symbols],
                                    return_exceptions=True,
                                )
                                for item in results:
                                    if isinstance(item, Exception):
                                        continue
                                    sym, t = item
                                    if t is not None:
                                        tickers[sym] = t

                            if tickers:
                                await self._write_spot_tickers_to_redis(exchange_provider, tickers)

                            orderbook_symbols = (config_spot_symbols or spot_ticker_symbols)[:_MAX_ORDERBOOK_SYMBOLS]
                            await self._write_spot_orderbooks_to_redis(exchange_provider, spot, orderbook_symbols)

                        futures_symbols = []
                        if futures_markets_ok:
                            fmarkets = getattr(futures, "markets", None) or {}
                            if fmarkets:
                                futures_symbols = [s for s in fmarkets.keys() if s.endswith(":USDT")]
                                futures_symbols.sort()
                        if not futures_symbols:
                            futures_symbols = self._map_to_futures_symbols(futures, spot_ticker_symbols or [])
                        if not futures_markets_ok and not futures_symbols:
                            futures_symbols = [s for s in (spot_ticker_symbols or []) if s.endswith("/USDT")]

                        if futures_symbols:
                            futures_symbols_usdt = [s for s in futures_symbols if "USDT" in s]
                            if futures_symbols_usdt:
                                futures_symbols_usdt = futures_symbols_usdt[:_MAX_FUTURES_TICKER_SYMBOLS]
                                futures_symbol_count = len(futures_symbols_usdt)
                                futures_tickers: dict = {}
                                semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

                                async def _fetch_future(sym: str):
                                    async with semaphore:
                                        try:
                                            ticker = None
                                            base_symbol = _normalize_symbol(sym)
                                            try_symbols = [sym]
                                            if base_symbol != sym:
                                                try_symbols.append(base_symbol)
                                            if ":" not in sym and sym.endswith("/USDT"):
                                                try_symbols.append(f"{sym}:USDT")
                                            for s in try_symbols:
                                                try:
                                                    ticker = await futures.fetch_ticker(s)
                                                    break
                                                except Exception:
                                                    continue
                                            return base_symbol, ticker
                                        except Exception:
                                            return None

                                results = await asyncio.gather(
                                    *[_fetch_future(symbol) for symbol in futures_symbols_usdt],
                                    return_exceptions=True,
                                )
                                for item in results:
                                    if isinstance(item, Exception) or not item:
                                        continue
                                    base_symbol, ticker = item
                                    if ticker is not None:
                                        futures_tickers[base_symbol] = ticker

                                if futures_tickers:
                                    await self._write_futures_tickers_to_redis(exchange_provider, futures_tickers)

                                funding_symbols = futures_symbols_usdt[: min(_MAX_FUNDING_SYMBOLS, len(futures_symbols_usdt))]
                                funding_symbol_count = len(funding_symbols)
                                funding = await self._fetch_funding_rates(
                                    futures,
                                    funding_symbols,
                                )
                                if funding:
                                    await self._write_funding_to_redis(exchange_provider, funding)
                    except Exception:
                        logger.exception("MarketDataService loop error")

                    try:
                        await self._write_metrics(
                            spot_symbol_count=spot_symbol_count,
                            futures_symbol_count=futures_symbol_count,
                            funding_symbol_count=funding_symbol_count,
                            elapsed_ms=(time.time() - start_ts) * 1000,
                        )
                    except Exception:
                        pass

                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_seconds)
                    except asyncio.TimeoutError:
                        pass

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"MarketDataService polling setup error: {e}")
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=_RETRY_DELAY_SECONDS)
                except asyncio.TimeoutError:
                    pass
            finally:
                if spot:
                    try:
                        await spot.close()
                    except Exception:
                        pass
                if futures:
                    try:
                        await futures.close()
                    except Exception:
                        pass
                if spot_session:
                    try:
                        await spot_session.close()
                    except Exception:
                        pass
                if futures_session:
                    try:
                        await futures_session.close()
                    except Exception:
                        pass

    async def _run_futures_polling_only(self) -> None:
        futures = None
        futures_session = None
        try:
            futures = ccxt.binance({
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
            })
            futures_session = _create_threaded_dns_session()
            futures.session = futures_session
            await futures.load_markets()

            while not self._stop_event.is_set():
                start_ts = time.time()
                futures_symbol_count = 0
                funding_symbol_count = 0
                try:
                    spot_symbols = await self._get_symbols_for_exchange(exchange_provider, limit=_MAX_TICKER_SYMBOLS)
                    if spot_symbols:
                        futures_symbols = self._map_to_futures_symbols(futures, spot_symbols)
                        if futures_symbols:
                            futures_symbols_usdt = [s for s in futures_symbols if "USDT" in s]
                            if futures_symbols_usdt:
                                futures_symbol_count = len(futures_symbols_usdt)
                                futures_tickers: dict = {}
                                semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

                                async def _fetch_future(sym: str):
                                    async with semaphore:
                                        try:
                                            return sym, await futures.fetch_ticker(sym)
                                        except Exception:
                                            return sym, None

                                results = await asyncio.gather(
                                    *[_fetch_future(s) for s in futures_symbols_usdt],
                                    return_exceptions=True,
                                )
                                for item in results:
                                    if isinstance(item, Exception):
                                        continue
                                    sym, ticker = item
                                    if ticker is not None:
                                        futures_tickers[sym] = ticker
                                if futures_tickers:
                                    await self._write_futures_tickers_to_redis(exchange_provider, futures_tickers)

                                funding_symbols = futures_symbols_usdt[: min(10, len(futures_symbols_usdt))]
                                funding_symbol_count = len(funding_symbols)
                                funding = await self._fetch_funding_rates(futures, funding_symbols)
                                if funding:
                                    await self._write_funding_to_redis(exchange_provider, funding)
                except Exception:
                    logger.exception("MarketDataService futures polling loop error")

                try:
                    await self._write_metrics(
                        spot_symbol_count=0,
                        futures_symbol_count=futures_symbol_count,
                        funding_symbol_count=funding_symbol_count,
                        elapsed_ms=(time.time() - start_ts) * 1000,
                    )
                except Exception:
                    pass

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=max(0.5, self._poll_interval_seconds))
                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"MarketDataService futures polling setup error: {e}")
        finally:
            if futures:
                try:
                    await futures.close()
                except Exception:
                    pass
            if futures_session:
                try:
                    await futures_session.close()
                except Exception:
                    pass

    async def _get_symbols_for_exchange(self, exchange_id: str, limit: int) -> list[str]:
        try:
            config = await get_config_service()
            pairs = await config.get_pairs_for_exchange(exchange_id)
            symbols = [p.symbol for p in pairs if p.is_active]
            symbols.sort()
            return symbols[:limit]
        except Exception:
            symbols = []
            for p in DEFAULT_PAIRS:
                if not p.is_active:
                    continue
                if p.supported_exchanges and exchange_id not in p.supported_exchanges:
                    continue
                symbols.append(p.symbol)
            return symbols[:limit]

    def _merge_symbol_priority(self, primary: list[str], fallback: list[str], limit: int) -> list[str]:
        seen = set()
        merged: list[str] = []
        for s in primary or []:
            if s in seen:
                continue
            merged.append(s)
            seen.add(s)
            if len(merged) >= limit:
                return merged
        for s in fallback or []:
            if s in seen:
                continue
            merged.append(s)
            seen.add(s)
            if len(merged) >= limit:
                break
        return merged

    def _map_to_futures_symbols(self, futures_exchange, spot_symbols: list[str]) -> list[str]:
        markets = getattr(futures_exchange, "markets", None) or {}
        out: list[str] = []
        for s in spot_symbols:
            if s in markets:
                out.append(s)
                continue
            if s.endswith("/USDT"):
                candidate = f"{s}:USDT"
                if candidate in markets:
                    out.append(candidate)
        return out

    async def _write_spot_tickers_to_redis(self, exchange_id: str, tickers: dict) -> None:
        await self._write_tickers_to_redis(f"ticker:{exchange_id}", tickers, ttl_seconds=_SPOT_TICKER_TTL_SECONDS)

    async def _write_futures_tickers_to_redis(self, exchange_id: str, tickers: dict) -> None:
        normalized = {}
        for symbol, t in (tickers or {}).items():
            normalized[_normalize_symbol(symbol)] = t
        await self._write_tickers_to_redis(
            f"ticker_futures:{exchange_id}",
            normalized,
            ttl_seconds=_FUTURES_TICKER_TTL_SECONDS,
        )

    async def _write_tickers_to_redis(self, key_prefix: str, tickers: dict, ttl_seconds: int) -> None:
        redis = await get_redis()
        now_ms = int(time.time() * 1000)
        index_key = f"symbols:{key_prefix}"

        pipe = redis.pipeline()
        written_count = 0
        stale_count = 0
        max_age_ms = None
        max_age_symbol = None
        for symbol, t in (tickers or {}).items():
            if not isinstance(t, dict):
                continue

            bid = t.get("bid")
            ask = t.get("ask")
            last = t.get("last")
            if last is not None:
                if bid is None:
                    bid = last
                if ask is None:
                    ask = last
            if bid is None and ask is None and last is None:
                continue

            key = f"{key_prefix}:{symbol}"
            exchange_ts = t.get("timestamp")
            try:
                exchange_ts = (
                    int(float(exchange_ts)) if exchange_ts is not None and str(exchange_ts).strip() != "" else None
                )
            except Exception:
                exchange_ts = None
            if exchange_ts is not None and exchange_ts < 1_000_000_000_000:
                exchange_ts *= 1000
            # 记录交易所时间戳，但以本地写入时间作为 freshness 判断
            ingest_ts = now_ms
            age_ms = now_ms - int(exchange_ts) if exchange_ts is not None else None
            if age_ms is not None and age_ms > 15000:
                stale_count += 1
                if max_age_ms is None or age_ms > max_age_ms:
                    max_age_ms = age_ms
                    max_age_symbol = symbol
            mapping = {
                "bid": "" if bid is None else str(bid),
                "ask": "" if ask is None else str(ask),
                "last": "" if last is None else str(last),
                "volume": "" if t.get("quoteVolume") is None else str(t.get("quoteVolume")),
                "timestamp": str(ingest_ts),
                "exchange_timestamp": "" if exchange_ts is None else str(exchange_ts),
            }
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, ttl_seconds)
            pipe.sadd(index_key, symbol)
            written_count += 1

        try:
            pipe.expire(index_key, max(60, ttl_seconds * 6))
            await pipe.execute()
        except Exception:
            logger.exception("Failed to write tickers to redis")

    async def _write_spot_orderbooks_to_redis(self, exchange_id: str, spot_exchange, symbols: list[str]) -> None:
        if not symbols:
            return

        redis = await get_redis()
        pipe = redis.pipeline()

        semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

        async def _fetch(symbol: str):
            async with semaphore:
                try:
                    ob = await spot_exchange.fetch_order_book(symbol, limit=_ORDERBOOK_LIMIT)
                    return symbol, ob
                except Exception:
                    return symbol, None

        results = await asyncio.gather(*[_fetch(s) for s in symbols], return_exceptions=True)
        ok_count = 0
        none_count = 0
        exception_count = 0
        for item in results:
            if isinstance(item, Exception):
                exception_count += 1
                continue
            if not item or not isinstance(item, tuple):
                none_count += 1
                continue
            symbol, ob = item
            if ob is None:
                none_count += 1
                continue
            ok_count += 1
            await self._write_orderbook_snapshot_to_redis(exchange_id, symbol, ob, pipe=pipe)

        try:
            await pipe.execute()
        except Exception:
            logger.exception("Failed to write orderbooks to redis")

    async def _run_ccxt_pro(self) -> None:
        ccxtpro = _try_import_ccxt_pro()
        if ccxtpro is None:
            logger.warning("ccxt.pro 未安装或不可用，回退到轮询模式")
            await self._run_polling()
            return

        exchange_provider = os.getenv("EXCHANGE_PROVIDER", "binance").lower()
        logger.info(f"MarketDataService ccxt.pro using exchange: {exchange_provider}")

        while not self._stop_event.is_set():
            spot = None
            futures = None
            spot_session = None
            futures_session = None
            tasks: list[asyncio.Task] = []
            futures_polling_task: Optional[asyncio.Task] = None

            try:
                if exchange_provider == "okx":
                    spot = ccxtpro.okx({
                        "apiKey": os.getenv("OKX_API_KEY"),
                        "secret": os.getenv("OKX_API_SECRET"),
                        "password": os.getenv("OKX_PASSPHRASE"),
                        "enableRateLimit": True,
                        "options": {"defaultType": "spot"},
                    })
                    futures = ccxtpro.okx({
                        "apiKey": os.getenv("OKX_API_KEY"),
                        "secret": os.getenv("OKX_API_SECRET"),
                        "password": os.getenv("OKX_PASSPHRASE"),
                        "enableRateLimit": True,
                        "options": {"defaultType": "swap"},
                    })
                else:
                    spot = ccxtpro.binance({
                        "enableRateLimit": True,
                        "options": {"defaultType": "spot"},
                    })
                    futures = ccxtpro.binance({
                        "enableRateLimit": True,
                        "options": {"defaultType": "future"},
                    })

                spot_session = _create_threaded_dns_session()
                futures_session = _create_threaded_dns_session()
                spot.session = spot_session
                futures.session = futures_session

                await spot.load_markets()

                futures_ok = True
                try:
                    await futures.load_markets()
                except Exception as e:
                    futures_ok = False
                    logger.warning(f"MarketDataService futures(ws) init failed, fallback to polling: {e}")

                spot_symbols = await self._get_symbols_for_exchange(exchange_provider, limit=_MAX_TICKER_SYMBOLS)
                if not spot_symbols:
                    logger.warning("ccxt.pro 模式：未找到可订阅的 trading_pairs")
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=_RETRY_DELAY_SECONDS)
                    except asyncio.TimeoutError:
                        pass
                    continue

                orderbook_symbols = spot_symbols[:_MAX_ORDERBOOK_SYMBOLS]
                futures_symbols = self._map_to_futures_symbols(futures, spot_symbols) if futures_ok else []

                for symbol in spot_symbols:
                    tasks.append(asyncio.create_task(self._pro_watch_spot_ticker(spot, exchange_provider, symbol)))

                for symbol in orderbook_symbols:
                    tasks.append(asyncio.create_task(self._pro_watch_spot_orderbook(spot, exchange_provider, symbol)))

                if futures_ok:
                    for symbol in futures_symbols:
                        tasks.append(asyncio.create_task(self._pro_watch_futures_ticker(futures, exchange_provider, symbol)))

                    for symbol in [s for s in futures_symbols if "USDT" in s][: min(10, len(futures_symbols))]:
                        tasks.append(asyncio.create_task(self._pro_watch_funding(futures, exchange_provider, symbol)))
                else:
                    futures_polling_task = asyncio.create_task(self._run_futures_polling_only())

                while not self._stop_event.is_set():
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"MarketDataService ccxt.pro setup error: {e}")
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=_RETRY_DELAY_SECONDS)
                except asyncio.TimeoutError:
                    pass
            finally:
                for t in tasks:
                    t.cancel()
                for t in tasks:
                    try:
                        await t
                    except Exception:
                        pass

                if futures_polling_task:
                    futures_polling_task.cancel()
                    try:
                        await futures_polling_task
                    except Exception:
                        pass

                if spot:
                    try:
                        await spot.close()
                    except Exception:
                        pass

                if futures:
                    try:
                        await futures.close()
                    except Exception:
                        pass

                if spot_session:
                    try:
                        await spot_session.close()
                    except Exception:
                        pass

                if futures_session:
                    try:
                        await futures_session.close()
                    except Exception:
                        pass

    async def _pro_watch_spot_ticker(self, exchange, exchange_id: str, symbol: str) -> None:
        failures = 0
        while not self._stop_event.is_set():
            try:
                ticker = await asyncio.wait_for(exchange.watch_ticker(symbol), timeout=5.0)
                await self._write_spot_tickers_to_redis(exchange_id, {symbol: ticker})
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
                try:
                    ticker = await exchange.fetch_ticker(symbol)
                    await self._write_spot_tickers_to_redis(exchange_id, {symbol: ticker})
                except Exception as e:
                    if failures % 20 == 0:
                        logger.warning(f"spot ticker update failed for {symbol}: {e}")
                await asyncio.sleep(1)

    async def _pro_watch_futures_ticker(self, exchange, exchange_id: str, symbol: str) -> None:
        failures = 0
        while not self._stop_event.is_set():
            try:
                ticker = await asyncio.wait_for(exchange.watch_ticker(symbol), timeout=5.0)
                await self._write_futures_tickers_to_redis(exchange_id, {symbol: ticker})
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
                try:
                    ticker = await exchange.fetch_ticker(symbol)
                    await self._write_futures_tickers_to_redis(exchange_id, {symbol: ticker})
                except Exception as e:
                    if failures % 20 == 0:
                        logger.warning(f"futures ticker update failed for {symbol}: {e}")
                await asyncio.sleep(1)

    async def _pro_watch_funding(self, exchange, exchange_id: str, symbol: str) -> None:
        use_watch = True
        while not self._stop_event.is_set():
            try:
                fr = None
                try_symbols = [symbol]
                if ":" not in symbol and symbol.endswith("/USDT"):
                    try_symbols.append(f"{symbol}:USDT")

                for s in try_symbols:
                    try:
                        if use_watch and hasattr(exchange, "watch_funding_rate"):
                            fr = await exchange.watch_funding_rate(s)
                        else:
                            fr = await exchange.fetch_funding_rate(s)
                    except Exception as e:
                        msg = str(e)
                        if use_watch and ("not supported" in msg or "not supported yet" in msg):
                            use_watch = False
                            continue
                        continue

                    if isinstance(fr, dict):
                        await self._write_funding_to_redis(exchange_id, {_normalize_symbol(symbol): fr})
                        break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"funding update failed for {symbol}: {e}")
                await asyncio.sleep(10)

    async def _pro_watch_spot_orderbook(self, exchange, exchange_id: str, symbol: str) -> None:
        failures = 0
        while not self._stop_event.is_set():
            try:
                ob = await asyncio.wait_for(
                    exchange.watch_order_book(symbol, limit=_ORDERBOOK_LIMIT),
                    timeout=5.0,
                )
                # ccxt.pro 返回结构与 fetch_order_book 基本一致
                await self._write_orderbook_snapshot_to_redis(exchange_id, symbol, ob)
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
                try:
                    ob = await exchange.fetch_order_book(symbol, limit=_ORDERBOOK_LIMIT)
                    await self._write_orderbook_snapshot_to_redis(exchange_id, symbol, ob)
                except Exception as e:
                    if failures % 20 == 0:
                        logger.warning(f"spot orderbook update failed for {symbol}: {e}")
                await asyncio.sleep(1)

    async def _write_orderbook_snapshot_to_redis(self, exchange_id: str, symbol: str, ob: dict, pipe=None) -> None:
        if not isinstance(ob, dict):
            return

        redis = await get_redis()
        local_pipe = pipe or redis.pipeline()
        now_ms = str(int(time.time() * 1000))
        index_key = f"symbols:orderbook:{exchange_id}"

        bids = (ob or {}).get("bids") or []
        asks = (ob or {}).get("asks") or []
        bids_key = f"orderbook:{exchange_id}:{symbol}:bids"
        asks_key = f"orderbook:{exchange_id}:{symbol}:asks"
        ts_key = f"orderbook:{exchange_id}:{symbol}:ts"

        local_pipe.delete(bids_key)
        local_pipe.delete(asks_key)

        bid_members = {}
        for bid_item in bids[:_ORDERBOOK_LIMIT]:
            # OKX返回 [price, amount, num_orders, ...], 只取前两个
            price, amount = bid_item[0], bid_item[1]
            bid_members[f"{price}:{amount}"] = float(price)
        if bid_members:
            local_pipe.zadd(bids_key, bid_members)
            local_pipe.expire(bids_key, _ORDERBOOK_TTL_SECONDS)

        ask_members = {}
        for ask_item in asks[:_ORDERBOOK_LIMIT]:
            # OKX返回 [price, amount, num_orders, ...], 只取前两个
            price, amount = ask_item[0], ask_item[1]
            ask_members[f"{price}:{amount}"] = float(price)
        if ask_members:
            local_pipe.zadd(asks_key, ask_members)
            local_pipe.expire(asks_key, _ORDERBOOK_TTL_SECONDS)

        local_pipe.set(ts_key, now_ms, ex=_ORDERBOOK_TTL_SECONDS)
        local_pipe.sadd(index_key, symbol)
        local_pipe.expire(index_key, max(60, _ORDERBOOK_TTL_SECONDS * 6))

        if pipe is None:
            try:
                await local_pipe.execute()
            except Exception:
                logger.exception("Failed to write orderbook snapshot to redis")

    async def _fetch_funding_rates(self, futures_exchange, symbols: list[str]) -> dict[str, dict]:
        result: dict[str, dict] = {}
        semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

        async def _fetch(symbol: str):
            async with semaphore:
                fr = None
                try_symbols = [symbol]
                if ":" not in symbol and symbol.endswith("/USDT"):
                    try_symbols.append(f"{symbol}:USDT")

                for s in try_symbols:
                    try:
                        fr = await futures_exchange.fetch_funding_rate(s)
                    except Exception:
                        continue

                    if isinstance(fr, dict):
                        return _normalize_symbol(symbol), fr
            return None

        results = await asyncio.gather(*[_fetch(s) for s in symbols], return_exceptions=True)
        for item in results:
            if isinstance(item, Exception) or not item:
                continue
            sym, fr = item
            result[sym] = fr
        return result

    async def _write_funding_to_redis(self, exchange_id: str, funding: dict[str, dict]) -> None:
        redis = await get_redis()
        now_ms = int(time.time() * 1000)
        pipe = redis.pipeline()
        index_key = f"symbols:funding:{exchange_id}"

        for symbol, fr in funding.items():
            if not isinstance(fr, dict):
                continue

            key = f"funding:{exchange_id}:{symbol}"
            mapping = {
                "rate": "" if fr.get("fundingRate") is None else str(fr.get("fundingRate")),
                "next_time": "" if fr.get("fundingTimestamp") is None else str(fr.get("fundingTimestamp")),
                "timestamp": str(fr.get("timestamp") or now_ms),
                "mark": "" if fr.get("markPrice") is None else str(fr.get("markPrice")),
                "index": "" if fr.get("indexPrice") is None else str(fr.get("indexPrice")),
            }
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, _FUNDING_TTL_SECONDS)
            pipe.sadd(index_key, symbol)

        try:
            pipe.expire(index_key, max(60, _FUNDING_TTL_SECONDS * 2))
            await pipe.execute()
        except Exception:
            logger.exception("Failed to write funding rates to redis")

    async def _write_metrics(
        self,
        *,
        spot_symbol_count: int,
        futures_symbol_count: int,
        funding_symbol_count: int,
        elapsed_ms: float,
    ) -> None:
        now = time.time()
        if (now - self._last_metrics_ts) < 5:
            return
        redis = await get_redis()
        key = "metrics:market_data_service"
        await redis.hset(
            key,
            mapping={
                "spot_symbols": str(spot_symbol_count),
                "futures_symbols": str(futures_symbol_count),
                "funding_symbols": str(funding_symbol_count),
                "last_loop_ms": f"{elapsed_ms:.1f}",
                "timestamp_ms": str(int(now * 1000)),
            },
        )
        await redis.expire(key, 120)
        self._last_metrics_ts = now


def _should_use_ccxt_pro() -> bool:
    return os.getenv("INARBIT_USE_CCXTPRO", "0").strip() in {"1", "true", "True"}


def _try_import_ccxt_pro():
    try:
        import ccxt.pro as ccxtpro  # type: ignore

        return ccxtpro
    except Exception:
        try:
            import ccxtpro  # type: ignore

            return ccxtpro
        except Exception:
            return None


def _normalize_symbol(symbol: str) -> str:
    return symbol.split(":", 1)[0]


def _create_threaded_dns_session() -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(resolver=ThreadedResolver(), ttl_dns_cache=300)
    return aiohttp.ClientSession(connector=connector)
