"""
Realtime overview cache stored in Redis.
No new database tables are introduced.
"""
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..db import get_pg_pool, get_redis


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _iso(ts: Optional[datetime]) -> str:
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return datetime.now(timezone.utc).isoformat()


async def _build_summary(conn, user_id: str) -> Dict[str, Any]:
    settings = await conn.fetchrow(
        """
        SELECT trading_mode, bot_status, default_strategy
        FROM global_settings
        WHERE user_id = $1
        """,
        user_id,
    )
    sim = await conn.fetchrow(
        """
        SELECT initial_capital, current_balance, quote_currency
        FROM simulation_config
        WHERE user_id = $1
        """,
        user_id,
    )
    strategy_rows = await conn.fetch(
        """
        SELECT name, strategy_type
        FROM strategy_configs
        WHERE user_id = $1 AND is_enabled = true
        ORDER BY priority ASC, name ASC
        """,
        user_id,
    )
    exchange_rows = await conn.fetch(
        """
        SELECT ec.exchange_id,
               COALESCE(ec.display_name, ec.exchange_id) AS display_name,
               COALESCE(es.is_connected, false) AS is_connected
        FROM exchange_configs ec
        LEFT JOIN exchange_status es ON es.exchange_id = ec.exchange_id
        WHERE ec.user_id = $1
          AND ec.is_active = true
          AND (ec.deleted_at IS NULL OR ec.deleted_at > NOW())
        ORDER BY ec.exchange_id
        """,
        user_id,
    )
    try:
        pair_rows = await conn.fetch(
            """
            SELECT tp.symbol
            FROM exchange_trading_pairs etp
            JOIN exchange_configs ec ON ec.id = etp.exchange_config_id
            JOIN trading_pairs tp ON tp.id = etp.trading_pair_id
            WHERE ec.user_id = $1
              AND ec.is_active = true
              AND etp.is_enabled = true
              AND tp.is_active = true
            ORDER BY tp.symbol
            LIMIT 8
            """,
            user_id,
        )
    except Exception:
        pair_rows = await conn.fetch(
            """
            SELECT symbol
            FROM trading_pairs
            WHERE is_active = true
            ORDER BY symbol
            LIMIT 8
            """
        )

    strategies = [row["name"] for row in strategy_rows if row.get("name")]
    strategy_types = [row["strategy_type"] for row in strategy_rows if row.get("strategy_type")]
    exchanges = [row["display_name"] for row in exchange_rows if row.get("is_connected")]
    exchange_ids = [row["exchange_id"] for row in exchange_rows if row.get("is_connected")]
    pairs = [row["symbol"] for row in pair_rows if row.get("symbol")]

    initial_capital = _safe_float(sim["initial_capital"] if sim else 0.0)
    current_balance = _safe_float(sim["current_balance"] if sim else 0.0)
    quote_currency = (sim["quote_currency"] if sim else "USDT") or "USDT"

    return {
        "trading_mode": (settings["trading_mode"] if settings else "paper") or "paper",
        "bot_status": (settings["bot_status"] if settings else "stopped") or "stopped",
        "default_strategy": (settings["default_strategy"] if settings else None),
        "strategies": strategies,
        "strategy_types": strategy_types,
        "exchanges": exchanges,
        "exchange_ids": exchange_ids,
        "pairs": pairs,
        "initial_capital": initial_capital,
        "current_balance": current_balance,
        "net_profit": round(current_balance - initial_capital, 6),
        "quote_currency": quote_currency,
    }


async def _build_profit_curve(conn, user_id: str, limit: int = 120) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT pr.executed_at, pr.net_profit
        FROM pnl_records pr
        JOIN strategy_configs sc ON sc.id = pr.strategy_id
        WHERE sc.user_id = $1
        ORDER BY pr.executed_at DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    if not rows:
        return [{"timestamp": _iso(None), "value": 0.0}]
    rows = list(reversed(rows))
    acc = 0.0
    series = []
    for row in rows:
        acc += _safe_float(row.get("net_profit"))
        series.append({"timestamp": _iso(row.get("executed_at")), "value": round(acc, 6)})
    return series


async def _build_trades(conn, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT oh.created_at, oh.side, oh.symbol, oh.price, oh.amount, oh.exchange_id
        FROM order_history oh
        JOIN strategy_configs sc ON sc.id = oh.strategy_id
        WHERE sc.user_id = $1
        ORDER BY oh.created_at DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    trades = []
    for row in rows:
        trades.append(
            {
                "time": _iso(row.get("created_at")),
                "side": (row.get("side") or "").lower(),
                "symbol": row.get("symbol"),
                "price": _safe_float(row.get("price")),
                "amount": _safe_float(row.get("amount")),
                "exchange": row.get("exchange_id"),
            }
        )
    return trades


async def refresh_realtime_cache(
    user_id: str,
    redis=None,
    pool=None,
) -> Dict[str, Any]:
    redis = redis or await get_redis()
    pool = pool or await get_pg_pool()
    async with pool.acquire() as conn:
        summary = await _build_summary(conn, user_id)
        profit_curve = await _build_profit_curve(conn, user_id)
        trades = await _build_trades(conn, user_id)

    prefix = f"realtime:{user_id}"
    meta_key = f"{prefix}:meta"
    now = int(time.time())
    await redis.hset(meta_key, mapping={"last_refresh": now})
    await redis.hsetnx(meta_key, "started_at", now)
    await redis.set(f"{prefix}:summary", json.dumps(summary, ensure_ascii=False))
    await redis.set(f"{prefix}:profit_curve", json.dumps(profit_curve, ensure_ascii=False))
    await redis.set(f"{prefix}:trades", json.dumps(trades, ensure_ascii=False))

    return {
        "summary": summary,
        "profit_curve": profit_curve,
        "trades": trades,
        "last_refresh": now,
    }


async def get_realtime_snapshot(
    user_id: str,
    force_refresh: bool = False,
    refresh_interval_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    redis = await get_redis()
    pool = await get_pg_pool()
    prefix = f"realtime:{user_id}"
    meta_key = f"{prefix}:meta"
    summary_key = f"{prefix}:summary"
    curve_key = f"{prefix}:profit_curve"
    trades_key = f"{prefix}:trades"

    meta = await redis.hgetall(meta_key) or {}
    now = int(time.time())
    started_at = int(float(meta.get("started_at") or 0)) if meta else 0
    last_refresh = int(float(meta.get("last_refresh") or 0)) if meta else 0
    if not started_at:
        started_at = now
        await redis.hset(meta_key, "started_at", started_at)

    interval = refresh_interval_seconds
    if interval is None:
        try:
            interval = int(os.getenv("REALTIME_REFRESH_INTERVAL_SECONDS", "5").strip() or "5")
        except Exception:
            interval = 5

    summary_payload = None
    curve_payload = None
    trades_payload = None

    if not force_refresh and last_refresh and (now - last_refresh) <= interval:
        raw_summary = await redis.get(summary_key)
        raw_curve = await redis.get(curve_key)
        raw_trades = await redis.get(trades_key)
        if raw_summary:
            try:
                summary_payload = json.loads(raw_summary)
            except Exception:
                summary_payload = None
        if raw_curve:
            try:
                curve_payload = json.loads(raw_curve)
            except Exception:
                curve_payload = None
        if raw_trades:
            try:
                trades_payload = json.loads(raw_trades)
            except Exception:
                trades_payload = None

    if summary_payload is None or curve_payload is None or trades_payload is None or force_refresh:
        refreshed = await refresh_realtime_cache(user_id, redis=redis, pool=pool)
        summary_payload = refreshed["summary"]
        curve_payload = refreshed["profit_curve"]
        trades_payload = refreshed["trades"]
        last_refresh = refreshed["last_refresh"]

    return {
        "current_time": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": max(0, now - started_at),
        "summary": summary_payload or {},
        "profit_curve": curve_payload or [],
        "trades": trades_payload or [],
        "last_refresh": last_refresh,
    }


async def warm_realtime_cache() -> None:
    """Preload realtime snapshots for all users on startup."""
    pool = await get_pg_pool()
    redis = await get_redis()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM users")
    for row in rows:
        try:
            await refresh_realtime_cache(str(row["id"]), redis=redis, pool=pool)
        except Exception:
            continue
