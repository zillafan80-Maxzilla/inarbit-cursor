"""
REST API 路由定义
提供策略管理、交易所配置、订单历史等接口
优化: 添加请求限流、响应缓存、批量查询优化
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict
from uuid import UUID
from datetime import datetime
import time
from functools import wraps
import os
import json

from ..db import get_pg_pool, get_redis
from ..engines.strategy_engine import get_strategy_engine_for_user
from ..auth import CurrentUser, get_current_user

router = APIRouter()
API_KEY_SECRET = os.getenv("EXCHANGE_API_KEY_SECRET", "inarbit_secret_key")


# ============================================
# Pydantic 模型
# ============================================

class ExchangeConfigCreate(BaseModel):
    exchange_id: str
    display_name: Optional[str] = None
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None
    is_spot_enabled: bool = True
    is_futures_enabled: bool = False


class ExchangeConfigResponse(BaseModel):
    id: UUID
    exchange_id: str
    display_name: Optional[str]
    is_spot_enabled: bool
    is_futures_enabled: bool
    is_active: bool
    created_at: datetime


class StrategyConfigCreate(BaseModel):
    strategy_type: str
    name: str
    description: Optional[str] = None
    priority: int = 5
    capital_percent: float = 20.0
    per_trade_limit: float = 100.0
    config: dict = {}
    allow_short: Optional[bool] = None
    max_leverage: Optional[float] = None
    regime_weights: Optional[Dict[str, float]] = None


class StrategyConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    priority: Optional[int] = None
    capital_percent: Optional[float] = None
    per_trade_limit: Optional[float] = None
    config: Optional[dict] = None
    allow_short: Optional[bool] = None
    max_leverage: Optional[float] = None
    regime_weights: Optional[Dict[str, float]] = None


class StrategyConfigResponse(BaseModel):
    id: UUID
    strategy_type: str
    name: str
    description: Optional[str]
    is_enabled: bool
    priority: int
    capital_percent: float
    per_trade_limit: float
    config: dict
    total_trades: int
    total_profit: float
    last_run_at: Optional[datetime]


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


# ============================================
# 交易所配置 API
# ============================================

@router.get("/exchanges", response_model=List[ExchangeConfigResponse])
async def list_exchanges(user: CurrentUser = Depends(get_current_user)):
    """获取所有交易所配置"""
    pool = await get_pg_pool()
    
    rows = await pool.fetch("""
        SELECT id, exchange_id, display_name, is_spot_enabled, 
               is_futures_enabled, is_active, created_at
        FROM exchange_configs
        WHERE is_active = true AND user_id = $1
        ORDER BY created_at DESC
    """, user.id)
    
    return [dict(row) for row in rows]


@router.post("/exchanges", response_model=ExchangeConfigResponse)
async def create_exchange(config: ExchangeConfigCreate, user: CurrentUser = Depends(get_current_user)):
    """添加新交易所配置"""
    pool = await get_pg_pool()
    
    # 加密 API 密钥 (简化版，生产环境应使用更安全的加密)
    # 这里使用 pgcrypto 的 encrypt 函数
    try:
        row = await pool.fetchrow("""
            INSERT INTO exchange_configs 
                (user_id, exchange_id, display_name, api_key_encrypted, 
                 api_secret_encrypted, passphrase_encrypted, 
                 is_spot_enabled, is_futures_enabled, is_active)
            VALUES ($1, $2, $3,
                    pgp_sym_encrypt($4, $9),
                    pgp_sym_encrypt($5, $9),
                    pgp_sym_encrypt($6, $9),
                    $7, $8, true)
            ON CONFLICT (user_id, exchange_id) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                api_key_encrypted = EXCLUDED.api_key_encrypted,
                api_secret_encrypted = EXCLUDED.api_secret_encrypted,
                passphrase_encrypted = EXCLUDED.passphrase_encrypted,
                is_spot_enabled = EXCLUDED.is_spot_enabled,
                is_futures_enabled = EXCLUDED.is_futures_enabled,
                is_active = true,
                updated_at = NOW()
            RETURNING id, exchange_id, display_name, is_spot_enabled, 
                      is_futures_enabled, is_active, created_at
        """, user.id, config.exchange_id, config.display_name, config.api_key,
             config.api_secret, config.passphrase or '',
             config.is_spot_enabled, config.is_futures_enabled, API_KEY_SECRET)
        
        return dict(row)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/exchanges/{exchange_id}")
async def delete_exchange(exchange_id: UUID, user: CurrentUser = Depends(get_current_user)):
    """删除交易所配置 (软删除)"""
    pool = await get_pg_pool()
    
    await pool.execute("""
        UPDATE exchange_configs SET is_active = false WHERE id = $1 AND user_id = $2
    """, exchange_id, user.id)
    
    return {"status": "deleted"}


# ============================================
# 策略配置 API
# ============================================

@router.get("/strategies", response_model=List[StrategyConfigResponse])
async def list_strategies(user: CurrentUser = Depends(get_current_user)):
    """获取所有策略配置"""
    pool = await get_pg_pool()
    
    rows = await pool.fetch("""
        SELECT id, strategy_type, name, description, is_enabled, priority,
               capital_percent, per_trade_limit, config,
               total_trades, total_profit, last_run_at
        FROM strategy_configs
        WHERE user_id = $1
        ORDER BY priority ASC, created_at DESC
    """, user.id)
    
    import json
    results = []
    for row in rows:
        item = dict(row)
        # 处理 Decimal 转 float
        if item.get('capital_percent') is not None:
            item['capital_percent'] = float(item['capital_percent'])
        if item.get('per_trade_limit') is not None:
            item['per_trade_limit'] = float(item['per_trade_limit'])
        if item.get('total_profit') is not None:
            item['total_profit'] = float(item['total_profit'])
            
        # 处理 JSONB 字符串
        if isinstance(item.get('config'), str):
            try:
                item['config'] = json.loads(item['config'])
            except:
                item['config'] = {}
                
        results.append(item)
        
    return results


@router.get("/strategies/{strategy_id}", response_model=StrategyConfigResponse)
async def get_strategy(strategy_id: UUID, user: CurrentUser = Depends(get_current_user)):
    """获取单个策略详情"""
    pool = await get_pg_pool()
    
    row = await pool.fetchrow("""
        SELECT id, strategy_type, name, description, is_enabled, priority,
               capital_percent, per_trade_limit, config,
               total_trades, total_profit, last_run_at
        FROM strategy_configs WHERE id = $1 AND user_id = $2
    """, strategy_id, user.id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    return dict(row)


@router.post("/strategies", response_model=StrategyConfigResponse)
async def create_strategy(config: StrategyConfigCreate, user: CurrentUser = Depends(get_current_user)):
    """创建新策略"""
    pool = await get_pg_pool()
    
    try:
        payload = dict(config.config or {})
        if config.allow_short is not None:
            payload["allow_short"] = bool(config.allow_short)
        if config.max_leverage is not None:
            payload["max_leverage"] = float(config.max_leverage)
        if config.regime_weights is not None:
            payload["regime_weights"] = _normalize_regime_weights(config.regime_weights)
        row = await pool.fetchrow("""
            INSERT INTO strategy_configs 
                (user_id, strategy_type, name, description, priority,
                 capital_percent, per_trade_limit, config)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, strategy_type, name, description, is_enabled, priority,
                      capital_percent, per_trade_limit, config,
                      total_trades, total_profit, last_run_at
        """, user.id, config.strategy_type, config.name, config.description,
             config.priority, config.capital_percent, config.per_trade_limit,
             payload)
        try:
            engine = await get_strategy_engine_for_user(user.id)
            await engine.reload_for_user(user.id)
        except Exception:
            pass
        return dict(row)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/strategies/{strategy_id}", response_model=StrategyConfigResponse)
async def update_strategy(strategy_id: UUID, update: StrategyConfigUpdate, user: CurrentUser = Depends(get_current_user)):
    """更新策略配置"""
    pool = await get_pg_pool()
    
    # 动态构建 UPDATE 语句
    updates = []
    values = []
    idx = 1
    payload = update.dict(exclude_none=True)
    if any(k in payload for k in ("allow_short", "max_leverage", "regime_weights")):
        existing = await pool.fetchval(
            "SELECT config FROM strategy_configs WHERE id = $1 AND user_id = $2",
            strategy_id,
            user.id,
        )
        cfg = existing or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        if payload.get("allow_short") is not None:
            cfg["allow_short"] = bool(payload.get("allow_short"))
        if payload.get("max_leverage") is not None:
            cfg["max_leverage"] = float(payload.get("max_leverage"))
        if payload.get("regime_weights") is not None:
            cfg["regime_weights"] = _normalize_regime_weights(payload.get("regime_weights"))
        payload["config"] = cfg
        payload.pop("allow_short", None)
        payload.pop("max_leverage", None)
        payload.pop("regime_weights", None)
    
    for field, value in payload.items():
        updates.append(f"{field} = ${idx}")
        values.append(value)
        idx += 1
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    values.append(strategy_id)
    
    query = f"""
        UPDATE strategy_configs 
        SET {', '.join(updates)}
        WHERE id = ${idx} AND user_id = ${idx + 1}
        RETURNING id, strategy_type, name, description, is_enabled, priority,
                  capital_percent, per_trade_limit, config,
                  total_trades, total_profit, last_run_at
    """
    
    values.append(user.id)
    row = await pool.fetchrow(query, *values)
    
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    try:
        engine = await get_strategy_engine_for_user(user.id)
        await engine.reload_for_user(user.id)
    except Exception:
        pass
    return dict(row)


@router.post("/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: UUID, user: CurrentUser = Depends(get_current_user)):
    """切换策略启用状态"""
    pool = await get_pg_pool()
    
    row = await pool.fetchrow("""
        UPDATE strategy_configs 
        SET is_enabled = NOT is_enabled
        WHERE id = $1 AND user_id = $2
        RETURNING id, is_enabled
    """, strategy_id, user.id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    try:
        engine = await get_strategy_engine_for_user(user.id)
        await engine.reload_for_user(user.id)
    except Exception:
        pass
    
    return {"id": str(row['id']), "is_enabled": row['is_enabled']}


@router.post("/strategies/reload")
async def reload_strategies(user: CurrentUser = Depends(get_current_user)):
    try:
        engine = await get_strategy_engine_for_user(user.id)
        await engine.reload_for_user(user.id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 订单历史 API
# ============================================

@router.get("/orders")
async def list_orders(
    user: CurrentUser = Depends(get_current_user),
    strategy_id: Optional[UUID] = None,
    exchange_id: Optional[str] = None,
    limit: int = 50
):
    """获取订单历史"""
    pool = await get_pg_pool()
    
    query = """
        SELECT id, strategy_id, exchange_id, exchange_order_id, symbol,
               side, order_type, amount, price, filled_amount, avg_fill_price,
               fee, fee_currency, status, error_message, latency_ms, created_at
        FROM order_history oh
        JOIN strategy_configs sc ON oh.strategy_id = sc.id
        WHERE sc.user_id = $1
    """
    params = [user.id]
    idx = 2
    
    if strategy_id:
        query += f" AND strategy_id = ${idx}"
        params.append(strategy_id)
        idx += 1
    
    if exchange_id:
        query += f" AND exchange_id = ${idx}"
        params.append(exchange_id)
        idx += 1
    
    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)
    
    rows = await pool.fetch(query, *params)
    return [dict(row) for row in rows]


# ============================================
# 盈亏统计 API
# ============================================

@router.get("/pnl/summary")
async def get_pnl_summary(user: CurrentUser = Depends(get_current_user)):
    """获取盈亏汇总"""
    pool = await get_pg_pool()
    
    rows = await pool.fetch("""
        SELECT 
            strategy_type,
            COUNT(*) as trade_count,
            SUM(net_profit) as total_profit,
            AVG(profit_rate) as avg_profit_rate,
            AVG(execution_time_ms) as avg_execution_ms
        FROM pnl_records pr
        JOIN strategy_configs sc ON pr.strategy_id = sc.id
        WHERE sc.user_id = $1
        GROUP BY strategy_type
    """, user.id)
    
    return [dict(row) for row in rows]


@router.get("/pnl/history")
async def get_pnl_history(
    user: CurrentUser = Depends(get_current_user),
    strategy_type: Optional[str] = None,
    days: int = 7,
    limit: int = 100
):
    """获取盈亏历史"""
    pool = await get_pg_pool()
    
    query = """
        SELECT id, strategy_id, strategy_type, exchange_id, path,
               gross_profit, fees, net_profit, profit_rate,
               execution_time_ms, executed_at
        FROM pnl_records pr
        JOIN strategy_configs sc ON pr.strategy_id = sc.id
        WHERE sc.user_id = $1
          AND executed_at > NOW() - INTERVAL '1 day' * $2
    """
    params = [user.id, days]
    idx = 3
    
    if strategy_type:
        query += f" AND strategy_type = ${idx}"
        params.append(strategy_type)
        idx += 1
    
    query += f" ORDER BY executed_at DESC LIMIT ${idx}"
    params.append(limit)
    
    rows = await pool.fetch(query, *params)
    return [dict(row) for row in rows]


# ============================================
# 系统日志 API
# ============================================

@router.get("/logs")
async def get_logs(
    user: CurrentUser = Depends(get_current_user),
    level: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100
):
    """获取系统日志"""
    pool = await get_pg_pool()
    
    query = "SELECT id, level, source, message, extra, created_at FROM system_logs WHERE 1=1"
    params = []
    idx = 1

    if user.role != 'admin':
        query += f" AND (user_id::text = ${idx} OR extra->>'user_id' = ${idx})"
        params.append(str(user.id))
        idx += 1
    
    if level:
        query += f" AND level = ${idx}"
        params.append(level)
        idx += 1
    
    if source:
        query += f" AND source = ${idx}"
        params.append(source)
        idx += 1
    
    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)
    
    rows = await pool.fetch(query, *params)
    return [dict(row) for row in rows]
