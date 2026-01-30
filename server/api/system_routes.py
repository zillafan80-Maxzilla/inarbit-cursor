"""
系统管理 API 路由
提供系统重置、初始化等管理功能
"""
from fastapi import APIRouter, HTTPException, Depends
import asyncio
import json
import os
import time
from pydantic import BaseModel
from typing import Optional

from ..db import get_pg_pool, get_redis
from ..auth import CurrentUser, require_admin, get_current_user

router = APIRouter()


class ResetRequest(BaseModel):
    """重置请求"""
    confirm: bool = False
    new_admin_password: Optional[str] = "admin"
    initial_capital: float = 1000.0


@router.post("/reset")
async def reset_system(request: ResetRequest, user: CurrentUser = Depends(require_admin)):
    """
    系统一键重置
    清空所有数据并重新初始化
    """
    if not request.confirm:
        raise HTTPException(status_code=400, detail="请确认重置操作 (confirm=true)")
    
    try:
        pool = await get_pg_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                async def _table_exists(table_name: str) -> bool:
                    return bool(await conn.fetchval(
                        """
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = $1
                        """,
                        table_name,
                    ))

                async def _column_exists(table_name: str, column_name: str) -> bool:
                    return bool(await conn.fetchval(
                        """
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = $1 AND column_name = $2
                        """,
                        table_name,
                        column_name,
                    ))

                strategy_rows = await conn.fetch(
                    "SELECT id FROM strategy_configs WHERE user_id = $1",
                    user.id,
                )
                strategy_ids = [r["id"] for r in strategy_rows]

                tables_user_scoped = [
                    "paper_orders",
                    "live_orders",
                    "paper_fills",
                    "live_fills",
                    "paper_pnl",
                    "live_pnl",
                    "paper_execution_plans",
                    "live_execution_plans",
                    "paper_opportunities",
                    "live_opportunities",
                    "paper_positions",
                    "live_positions",
                    "paper_ledger_entries",
                    "live_ledger_entries",
                ]

                for table in tables_user_scoped:
                    if await _table_exists(table) and await _column_exists(table, "user_id"):
                        await conn.execute(f"DELETE FROM {table} WHERE user_id = $1", user.id)

                if strategy_ids:
                    for table in ["pnl_records", "order_history", "strategy_exchanges"]:
                        if await _table_exists(table) and await _column_exists(table, "strategy_id"):
                            await conn.execute(
                                f"DELETE FROM {table} WHERE strategy_id = ANY($1::uuid[])",
                                strategy_ids,
                            )

                if await _table_exists("exchange_configs"):
                    await conn.execute("DELETE FROM exchange_configs WHERE user_id = $1", user.id)
                if await _table_exists("simulation_config"):
                    await conn.execute("DELETE FROM simulation_config WHERE user_id = $1", user.id)
                if await _table_exists("global_settings"):
                    await conn.execute("DELETE FROM global_settings WHERE user_id = $1", user.id)
                if await _table_exists("strategy_configs"):
                    await conn.execute("DELETE FROM strategy_configs WHERE user_id = $1", user.id)

                # 2. 创建默认模拟配置
                await conn.execute("""
                    INSERT INTO simulation_config (user_id, initial_capital, current_balance, realized_pnl)
                    VALUES ($1, $2, $2, 0)
                """, user.id, request.initial_capital)
                
                # 3. 创建默认全局设置
                await conn.execute("""
                    INSERT INTO global_settings (user_id, trading_mode, bot_status, default_strategy)
                    VALUES ($1, 'paper', 'stopped', 'triangular')
                """, user.id)
                
                # 4. 创建默认策略
                strategies = [
                    ('triangular', '三角套利', '同交易所内三个交易对的价格差套利', 1),
                    ('graph', '图搜索套利', 'Bellman-Ford算法寻找N跳套利路径', 2),
                    ('funding_rate', '期现套利', '多现货+空永续合约，赚取资金费率', 3),
                    ('pair', '配对交易', '相关币种价差回归套利', 4),
                    ('grid', '网格交易', '区间内高抛低吸', 5),
                ]
                default_weights = {
                    "RANGE": 1.0,
                    "DOWNTREND": 0.6,
                    "UPTREND": 0.7,
                    "STRESS": 0.2,
                }
                
                for strategy_type, name, description, priority in strategies:
                    cfg = {
                        "regime_weights": default_weights,
                        "allow_short": strategy_type in {"funding_rate", "pair"},
                        "max_leverage": 1.0,
                    }
                    await conn.execute("""
                        INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, config)
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    """, user.id, strategy_type, name, description, priority, json.dumps(cfg, ensure_ascii=False))
        
        try:
            redis = await get_redis()
            await redis.delete(
                "decisions:latest",
                "opportunities:triangular",
                "opportunities:cashcarry",
                "metrics:decision_service",
                "metrics:triangular_service",
                "metrics:cashcarry_service",
                "metrics:market_data_service",
                "metrics:oms_service",
            )
        except Exception:
            pass

        return {
            "success": True,
            "message": "系统已重置",
            "admin_created": False,
            "initial_capital": request.initial_capital
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置失败: {str(e)}")


@router.get("/status")
async def get_system_status(user: CurrentUser = Depends(require_admin)):
    """获取系统状态"""
    try:
        pool = await get_pg_pool()
        
        async with pool.acquire() as conn:
            # 用户数
            user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            
            # 策略数
            strategy_count = await conn.fetchval("SELECT COUNT(*) FROM strategy_configs")
            
            # 交易所数
            exchange_count = await conn.fetchval("""
                SELECT COUNT(*) FROM exchange_configs WHERE is_active = true
            """)
            
            # 订单数
            order_count = await conn.fetchval("SELECT COUNT(*) FROM order_history")
            
            # 收益记录数
            pnl_count = await conn.fetchval("SELECT COUNT(*) FROM pnl_records")
        
        return {
            "success": True,
            "data": {
                "users": user_count,
                "strategies": strategy_count,
                "exchanges": exchange_count,
                "orders": order_count,
                "pnlRecords": pnl_count
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_system_metrics(user: CurrentUser = Depends(require_admin)):
    """获取系统关键指标"""
    try:
        redis = await get_redis()
        pipe = redis.pipeline()
        pipe.zcard("opportunities:triangular")
        pipe.zcard("opportunities:cashcarry")
        pipe.zcard("decisions:latest")
        pipe.get("decision:constraints:effective")
        pipe.hgetall("metrics:decision_service")
        pipe.hgetall("metrics:triangular_service")
        pipe.hgetall("metrics:cashcarry_service")
        pipe.hgetall("metrics:market_data_service")
        pipe.hgetall("metrics:oms_service")
        pipe.hgetall("metrics:market_regime")
        pipe.scard("symbols:ticker:binance")
        pipe.scard("symbols:ticker_futures:binance")
        pipe.scard("symbols:funding:binance")
        pipe.scard("symbols:orderbook:binance")
        try:
            (
                tri_count,
                cc_count,
                decision_count,
                constraints,
                decision_metrics,
                triangular_metrics,
                cashcarry_metrics,
                market_data_metrics,
                oms_metrics,
                market_regime_metrics,
                spot_symbol_count,
                futures_symbol_count,
                funding_symbol_count,
                orderbook_symbol_count,
            ) = await asyncio.wait_for(pipe.execute(), timeout=3)
        except asyncio.TimeoutError:
            fallback = {
                "opportunities": {"triangular": 0, "cashcarry": 0},
                "decisions": 0,
                "constraints": {},
                "decision_metrics": {},
                "triangular_metrics": {},
                "cashcarry_metrics": {},
                "market_data_metrics": {},
                "oms_metrics": {},
                "market_regime": {},
                "market_data": {
                    "symbols_spot": 0,
                    "symbols_futures": 0,
                    "symbols_funding": 0,
                    "symbols_orderbook": 0,
                },
                "health": {
                    "market_data_fresh": False,
                    "market_data_age_ms": None,
                    "market_data_max_age_ms": None,
                },
                "stale": True,
                "error": "metrics timeout",
            }
            return {"success": True, "data": fallback}

        constraints_payload = {}
        try:
            if constraints:
                constraints_payload = json.loads(constraints)
        except Exception:
            constraints_payload = {}

        now_ms = int(time.time() * 1000)
        md_ts = None
        try:
            if market_data_metrics and market_data_metrics.get("timestamp_ms"):
                md_ts = int(market_data_metrics.get("timestamp_ms"))
        except Exception:
            md_ts = None
        try:
            max_age = int(os.getenv("MARKETDATA_HEALTH_MAX_AGE_MS", "5000").strip() or "5000")
        except Exception:
            max_age = 5000
        md_age = (now_ms - md_ts) if md_ts else None
        md_fresh = True if (md_age is not None and md_age <= max_age) else False

        response = {
            "success": True,
            "data": {
                "opportunities": {
                    "triangular": int(tri_count or 0),
                    "cashcarry": int(cc_count or 0),
                },
                "decisions": int(decision_count or 0),
                "constraints": constraints_payload,
                "decision_metrics": decision_metrics or {},
                "triangular_metrics": triangular_metrics or {},
                "cashcarry_metrics": cashcarry_metrics or {},
                "market_data_metrics": market_data_metrics or {},
                "oms_metrics": oms_metrics or {},
                "market_regime": market_regime_metrics or {},
                "market_data": {
                    "symbols_spot": int(spot_symbol_count or 0),
                    "symbols_futures": int(futures_symbol_count or 0),
                    "symbols_funding": int(funding_symbol_count or 0),
                    "symbols_orderbook": int(orderbook_symbol_count or 0),
                },
                "health": {
                    "market_data_fresh": md_fresh,
                    "market_data_age_ms": md_age,
                    "market_data_max_age_ms": max_age,
                }
            },
        }
        try:
            await redis.set("metrics:system", json.dumps(response["data"], ensure_ascii=False), ex=60)
        except Exception:
            pass
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-exchange")
async def add_exchange_config(
    exchange_id: str,
    api_key: str,
    api_secret: str,
    passphrase: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
):
    """添加交易所 API 配置"""
    try:
        pool = await get_pg_pool()
        
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO exchange_configs (user_id, exchange_id, display_name, api_key_encrypted, api_secret_encrypted, passphrase_encrypted)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, exchange_id) DO UPDATE
                SET api_key_encrypted = $4, api_secret_encrypted = $5, passphrase_encrypted = $6, updated_at = NOW()
            """, user.id, exchange_id, exchange_id.capitalize(), api_key, api_secret, passphrase)
            
            await conn.execute("""
                UPDATE exchange_status SET last_heartbeat = NOW() WHERE exchange_id = $1
            """, exchange_id)
        
        return {
            "success": True,
            "message": f"交易所 {exchange_id} 配置已添加"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
