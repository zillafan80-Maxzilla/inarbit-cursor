"""
配置API路由
提供统一的配置数据接口，确保前端各模块获取一致的配置信息
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel

from ..services.config_service import get_config_service
from ..db import get_pg_pool, get_redis
from ..auth import CurrentUser, get_current_user

router = APIRouter()


class GlobalSettingsUpdate(BaseModel):
    tradingMode: Optional[str] = None
    defaultStrategy: Optional[str] = None
    riskLevel: Optional[str] = None
    maxDailyLoss: Optional[float] = None
    maxPositionSize: Optional[float] = None
    enableNotifications: Optional[bool] = None

class SimulationUpdate(BaseModel):
    initialCapital: Optional[float] = None
    quoteCurrency: Optional[str] = None
    resetOnStart: Optional[bool] = None
    resetNow: Optional[bool] = None

class OpportunityConfigUpdate(BaseModel):
    config: dict


# ============================================
# 交易所配置 API
# ============================================

@router.get("/exchanges")
async def get_exchanges(user: CurrentUser = Depends(get_current_user)):
    """
    获取所有交易所配置
    返回统一的交易所列表，确保所有前端页面使用相同数据
    """
    try:
        service = await get_config_service()
        exchanges = await service.get_all_exchanges(user_id=user.id)
        return {
            "success": True,
            "data": [ex.to_dict() for ex in exchanges],
            "count": len(exchanges)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exchanges/connected")
async def get_connected_exchanges(user: CurrentUser = Depends(get_current_user)):
    """获取已连接的交易所"""
    try:
        service = await get_config_service()
        exchanges = await service.get_connected_exchanges(user_id=user.id)
        return {
            "success": True,
            "data": [ex.to_dict() for ex in exchanges],
            "count": len(exchanges)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exchanges/{exchange_id}")
async def get_exchange(exchange_id: str, user: CurrentUser = Depends(get_current_user)):
    """获取指定交易所配置"""
    try:
        service = await get_config_service()
        exchange = await service.get_exchange(exchange_id, user_id=user.id)
        if not exchange:
            raise HTTPException(status_code=404, detail=f"交易所 {exchange_id} 不存在")
        return {
            "success": True,
            "data": exchange.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 交易对配置 API
# ============================================

@router.get("/pairs")
async def get_trading_pairs(exchange_id: Optional[str] = None, user: CurrentUser = Depends(get_current_user)):
    """
    获取交易对配置
    可选过滤指定交易所支持的交易对
    """
    try:
        service = await get_config_service()
        
        if exchange_id:
            pairs = await service.get_pairs_for_exchange(exchange_id, user_id=user.id)
        else:
            pairs = await service.get_all_pairs()
        
        return {
            "success": True,
            "data": [p.to_dict() for p in pairs],
            "count": len(pairs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pairs/{symbol}")
async def get_trading_pair(symbol: str, user: CurrentUser = Depends(get_current_user)):
    """获取指定交易对配置"""
    try:
        # 将URL中的-替换为/
        symbol = symbol.replace('-', '/')
        service = await get_config_service()
        pair = await service.get_pair(symbol)
        if not pair:
            raise HTTPException(status_code=404, detail=f"交易对 {symbol} 不存在")
        return {
            "success": True,
            "data": pair.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/currencies")
async def get_currencies():
    """获取所有基础货币列表"""
    try:
        service = await get_config_service()
        currencies = await service.get_base_currencies()
        return {
            "success": True,
            "data": currencies,
            "count": len(currencies)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 全局设置 API
# ============================================

@router.get("/opportunity")
async def list_opportunity_configs(user: CurrentUser = Depends(get_current_user)):
    """列出机会配置（Graph/Grid/Pair）"""
    try:
        service = await get_config_service()
        configs = await service.get_all_opportunity_configs(user_id=user.id)
        return {
            "success": True,
            "data": [c.to_dict() for c in configs],
            "count": len(configs),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/opportunity/{strategy_type}")
async def get_opportunity_config(strategy_type: str, user: CurrentUser = Depends(get_current_user)):
    """获取指定机会配置"""
    try:
        service = await get_config_service()
        config = await service.get_opportunity_config(strategy_type=strategy_type, user_id=user.id)
        return {"success": True, "data": config.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/opportunity/{strategy_type}")
async def update_opportunity_config(
    strategy_type: str,
    payload: OpportunityConfigUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """更新机会配置"""
    try:
        service = await get_config_service()
        updated = await service.update_opportunity_config(
            strategy_type=strategy_type,
            config=payload.config or {},
            user_id=user.id,
        )
        return {"success": True, "data": updated.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/global")
async def get_global_settings(user: CurrentUser = Depends(get_current_user)):
    """获取全局设置"""
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    gs.trading_mode,
                    gs.bot_status,
                    gs.default_strategy,
                    gs.risk_level,
                    gs.max_daily_loss,
                    gs.max_position_size,
                    gs.enable_notifications,
                    sc.initial_capital,
                    sc.current_balance,
                    sc.realized_pnl
                FROM global_settings gs
                LEFT JOIN simulation_config sc ON gs.user_id = sc.user_id
                WHERE gs.user_id = $1
            """, user.id)
            
            if not row:
                return {
                    "success": True,
                    "data": {
                        "tradingMode": "paper",
                        "botStatus": "stopped",
                        "defaultStrategy": "triangular",
                        "riskLevel": "medium"
                    }
                }
            
            return {
                "success": True,
                "data": {
                    "tradingMode": row['trading_mode'],
                    "botStatus": row['bot_status'],
                    "defaultStrategy": row['default_strategy'],
                    "riskLevel": row['risk_level'],
                    "maxDailyLoss": float(row['max_daily_loss']) if row['max_daily_loss'] else 500,
                    "maxPositionSize": float(row['max_position_size']) if row['max_position_size'] else 10000,
                    "enableNotifications": row['enable_notifications'],
                    "simulation": {
                        "initialCapital": float(row['initial_capital']) if row['initial_capital'] else 1000,
                        "currentBalance": float(row['current_balance']) if row['current_balance'] else 1000,
                        "realizedPnL": float(row['realized_pnl']) if row['realized_pnl'] else 0
                    }
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/refresh")
async def refresh_config_cache(user: CurrentUser = Depends(get_current_user)):
    """刷新配置缓存"""
    try:
        service = await get_config_service()
        await service.refresh_cache()
        return {
            "success": True,
            "message": "配置缓存已刷新"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/global")
async def update_global_settings(
    payload: GlobalSettingsUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    try:
        pool = await get_pg_pool()
        await pool.execute(
            """
            INSERT INTO global_settings (
                user_id,
                trading_mode,
                default_strategy,
                risk_level,
                max_daily_loss,
                max_position_size,
                enable_notifications,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET trading_mode = COALESCE(EXCLUDED.trading_mode, global_settings.trading_mode),
                default_strategy = COALESCE(EXCLUDED.default_strategy, global_settings.default_strategy),
                risk_level = COALESCE(EXCLUDED.risk_level, global_settings.risk_level),
                max_daily_loss = COALESCE(EXCLUDED.max_daily_loss, global_settings.max_daily_loss),
                max_position_size = COALESCE(EXCLUDED.max_position_size, global_settings.max_position_size),
                enable_notifications = COALESCE(EXCLUDED.enable_notifications, global_settings.enable_notifications),
                updated_at = NOW()
            """,
            user.id,
            payload.tradingMode,
            payload.defaultStrategy,
            payload.riskLevel,
            payload.maxDailyLoss,
            payload.maxPositionSize,
            payload.enableNotifications,
        )

        return await get_global_settings(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/simulation")
async def get_simulation_config(user: CurrentUser = Depends(get_current_user)):
    try:
        pool = await get_pg_pool()
        row = await pool.fetchrow(
            """
            SELECT initial_capital, quote_currency, current_balance,
                   realized_pnl, unrealized_pnl, total_trades, win_rate, reset_on_start
            FROM simulation_config
            WHERE user_id = $1
            """,
            user.id,
        )
        if not row:
            return {
                "success": True,
                "data": {
                    "initialCapital": 1000,
                    "quoteCurrency": "USDT",
                    "currentBalance": 1000,
                    "realizedPnL": 0,
                    "unrealizedPnL": 0,
                    "totalTrades": 0,
                    "winRate": 0,
                    "resetOnStart": False,
                },
            }

        return {
            "success": True,
            "data": {
                "initialCapital": float(row["initial_capital"] or 0),
                "quoteCurrency": row["quote_currency"] or "USDT",
                "currentBalance": float(row["current_balance"] or 0),
                "realizedPnL": float(row["realized_pnl"] or 0),
                "unrealizedPnL": float(row["unrealized_pnl"] or 0),
                "totalTrades": int(row["total_trades"] or 0),
                "winRate": float(row["win_rate"] or 0),
                "resetOnStart": bool(row["reset_on_start"]),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/simulation")
async def update_simulation_config(
    payload: SimulationUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    try:
        pool = await get_pg_pool()
        reset_now = bool(payload.resetNow)
        await pool.execute(
            """
            INSERT INTO simulation_config (
                user_id, initial_capital, quote_currency, current_balance,
                realized_pnl, unrealized_pnl, total_trades, win_rate, reset_on_start, updated_at
            )
            VALUES ($1, COALESCE($2, 1000), COALESCE($3, 'USDT'), COALESCE($4, 1000),
                    COALESCE($5, 0), COALESCE($6, 0), COALESCE($7, 0), COALESCE($8, 0), COALESCE($9, false), NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET initial_capital = COALESCE(EXCLUDED.initial_capital, simulation_config.initial_capital),
                quote_currency = COALESCE(EXCLUDED.quote_currency, simulation_config.quote_currency),
                reset_on_start = COALESCE(EXCLUDED.reset_on_start, simulation_config.reset_on_start),
                updated_at = NOW()
            """,
            user.id,
            payload.initialCapital,
            payload.quoteCurrency,
            payload.initialCapital,
            0,
            0,
            0,
            0,
            payload.resetOnStart,
        )

        if reset_now:
            await pool.execute(
                """
                UPDATE simulation_config
                SET current_balance = initial_capital,
                    realized_pnl = 0,
                    unrealized_pnl = 0,
                    total_trades = 0,
                    win_rate = 0,
                    reset_on_start = false,
                    updated_at = NOW()
                WHERE user_id = $1
                """,
                user.id,
            )

            await pool.execute(
                """
                DELETE FROM paper_pnl
                WHERE user_id = $1
                """,
                user.id,
            )

        return await get_simulation_config(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/simulation/portfolio")
async def get_simulation_portfolio(user: CurrentUser = Depends(get_current_user)):
    try:
        pool = await get_pg_pool()
        redis = await get_redis()

        sim = await pool.fetchrow(
            """
            SELECT initial_capital, quote_currency, current_balance,
                   realized_pnl, unrealized_pnl, total_trades, win_rate
            FROM simulation_config
            WHERE user_id = $1
            """,
            user.id,
        )
        quote_currency = (sim["quote_currency"] if sim else "USDT") or "USDT"

        rows = await pool.fetch(
            """
            SELECT exchange_id, account_type, instrument, quantity, avg_price, updated_at
            FROM paper_positions
            WHERE user_id = $1 AND quantity <> 0
            ORDER BY updated_at DESC
            """,
            user.id,
        )

        def _to_float(v):
            try:
                return float(v)
            except Exception:
                return 0.0

        def _price_from_ticker(ticker: dict):
            if not ticker:
                return None
            last = ticker.get("last") or ticker.get("close")
            if last is not None:
                return _to_float(last)
            bid = ticker.get("bid")
            ask = ticker.get("ask")
            if bid is not None and ask is not None:
                return (_to_float(bid) + _to_float(ask)) / 2
            if bid is not None:
                return _to_float(bid)
            if ask is not None:
                return _to_float(ask)
            return None

        by_exchange = {}
        total_value = 0.0
        unrealized_pnl_rt = 0.0

        for row in rows:
            exchange_id = row["exchange_id"]
            instrument = row["instrument"]
            quantity = _to_float(row["quantity"])

            symbol = instrument if "/" in instrument else f"{instrument}/{quote_currency}"
            price = 1.0 if instrument == quote_currency else None
            if price is None:
                key = f"ticker:{exchange_id}:{symbol}"
                ticker = await redis.hgetall(key)
                price = _price_from_ticker(ticker)

            value = quantity * price if price is not None else None
            avg_price = _to_float(row["avg_price"]) if row["avg_price"] is not None else None
            if price is not None and avg_price is not None:
                unrealized_pnl_rt += (price - avg_price) * quantity

            asset = {
                "coin": instrument,
                "symbol": symbol,
                "account_type": row["account_type"],
                "quantity": quantity,
                "avg_price": avg_price,
                "price": price,
                "value": value,
                "updated_at": row["updated_at"],
            }

            if exchange_id not in by_exchange:
                by_exchange[exchange_id] = {
                    "exchange_id": exchange_id,
                    "totalValue": 0.0,
                    "assets": [],
                }

            by_exchange[exchange_id]["assets"].append(asset)
            if value is not None:
                by_exchange[exchange_id]["totalValue"] += value
                total_value += value

        current_balance = float(sim["current_balance"] or 0) if sim else 1000
        realized_pnl = float(sim["realized_pnl"] or 0) if sim else 0
        total_equity = current_balance + total_value

        return {
            "success": True,
            "data": {
                "summary": {
                    "initialCapital": float(sim["initial_capital"] or 0) if sim else 1000,
                    "currentBalance": float(sim["current_balance"] or 0) if sim else 1000,
                    "realizedPnL": realized_pnl,
                    "unrealizedPnL": unrealized_pnl_rt,
                    "totalTrades": int(sim["total_trades"] or 0) if sim else 0,
                    "winRate": float(sim["win_rate"] or 0) if sim else 0,
                    "quoteCurrency": quote_currency,
                    "totalValue": total_value,
                    "totalEquity": total_equity,
                },
                "exchanges": list(by_exchange.values()),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
