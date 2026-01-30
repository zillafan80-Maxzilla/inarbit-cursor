"""
优化后的交易所管理API路由
支持完整的业务逻辑
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

from ..services.exchange_service import ExchangeService
from ..db import get_pg_pool
from ..auth import CurrentUser, get_current_user
from ..exchange.ccxt_exchange import CCXTExchange

router = APIRouter(prefix="/api/v2/exchanges", tags=["Exchanges V2"])


# ============================================
# Pydantic Models
# ============================================

class ExchangeSetupRequest(BaseModel):
    """新增交易所请求"""
    exchange_type: str  # 'binance', 'okx', etc.
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None
    display_name: Optional[str] = None


class ExchangeDeleteRequest(BaseModel):
    """删除交易所请求"""
    mode: str = "soft"  # 'soft' or 'hard'
    confirm_code: Optional[str] = None  # 硬删除时必需


class ExchangePairUpdate(BaseModel):
    """交易对启用状态更新"""
    trading_pair_id: UUID
    is_enabled: bool


# ============================================
# Exchange Configs List
# ============================================

@router.get("")
async def list_exchanges(user: CurrentUser = Depends(get_current_user)):
    """获取交易所配置列表（含 UUID）"""
    try:
        pool = await get_pg_pool()
        rows = await pool.fetch(
            """
            SELECT id, exchange_id, display_name, is_active, deleted_at, created_at
            FROM exchange_configs
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user.id,
        )
        return {
            "success": True,
            "data": [dict(r) for r in rows],
            "count": len(rows),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# API Endpoints
# ============================================

@router.post("/setup")
async def setup_exchange(request: ExchangeSetupRequest, user: CurrentUser = Depends(get_current_user)):
    """
    完整的交易所设置流程
    
    步骤：
    1. 验证API密钥
    2. 获取支持的交易对
    3. 保存配置
    4. 返回结果和推荐配置
    """
    try:
        result = await ExchangeService.setup_exchange(
            user_id=user.id,
            exchange_type=request.exchange_type,
            api_key=request.api_key,
            api_secret=request.api_secret,
            passphrase=request.passphrase,
            display_name=request.display_name
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{exchange_id}")
async def delete_exchange(
    exchange_id: UUID,
    request: ExchangeDeleteRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    删除交易所
    
    模式：
    - soft: 软删除，停用但保留历史数据（默认）
    - hard: 硬删除，永久删除所有相关数据（需要确认码）
    """
    try:
        if request.mode == "soft":
            result = await ExchangeService.soft_delete_exchange(
                exchange_id=exchange_id,
                user_id=user.id
            )
        elif request.mode == "hard":
            if not request.confirm_code:
                # 返回确认码供用户输入
                import hashlib
                confirm_code = hashlib.md5(f"DELETE-{exchange_id}".encode()).hexdigest()[:6].upper()
                raise HTTPException(
                    status_code=400, 
                    detail=f"硬删除需要确认码。请在请求中包含: confirm_code='{confirm_code}'"
                )
            
            result = await ExchangeService.hard_delete_exchange(
                exchange_id=exchange_id,
                user_id=user.id,
                confirm_code=request.confirm_code
            )
        else:
            raise HTTPException(status_code=400, detail="无效的删除模式")
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{exchange_id}/pairs")
async def get_exchange_pairs(
    exchange_id: UUID,
    enabled_only: bool = False,
    user: CurrentUser = Depends(get_current_user),
):
    """
    获取交易所的所有交易对
    """
    try:
        pool = await get_pg_pool()
        
        query = """
            SELECT 
                tp.id as pair_id,
                tp.symbol,
                tp.base_currency,
                tp.quote_currency,
                etp.is_enabled,
                etp.min_order_amount,
                etp.max_order_amount,
                etp.maker_fee,
                etp.taker_fee
            FROM exchange_trading_pairs etp
            JOIN trading_pairs tp ON etp.trading_pair_id = tp.id
            JOIN exchange_configs ec ON ec.id = etp.exchange_config_id
            WHERE etp.exchange_config_id = $1 AND ec.user_id = $2
        """
        
        if enabled_only:
            query += " AND etp.is_enabled = true"
        
        query += " ORDER BY tp.symbol"
        
        rows = await pool.fetch(query, exchange_id, user.id)
        
        return {
            'exchange_id': str(exchange_id),
            'pairs': [dict(row) for row in rows],
            'total': len(rows),
            'enabled': sum(1 for r in rows if r['is_enabled'])
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{exchange_id}/pairs/{pair_id}")
async def toggle_exchange_pair(
    exchange_id: UUID, 
    pair_id: UUID,
    update: ExchangePairUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """
    启用/禁用交易所的某个交易对
    """
    try:
        pool = await get_pg_pool()
        
        result = await pool.execute("""
            UPDATE exchange_trading_pairs 
            SET is_enabled = $1, updated_at = NOW()
            WHERE exchange_config_id = $2 AND trading_pair_id = $3
              AND EXISTS (
                SELECT 1 FROM exchange_configs ec WHERE ec.id = $2 AND ec.user_id = $4
              )
        """, update.is_enabled, exchange_id, pair_id, user.id)
        
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="交易对关联不存在")
        
        return {
            'success': True,
            'message': f"交易对已{'启用' if update.is_enabled else '禁用'}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{exchange_id}/stats")
async def get_exchange_stats(exchange_id: UUID, user: CurrentUser = Depends(get_current_user)):
    """
    获取交易所的统计信息
    """
    try:
        pool = await get_pg_pool()
        
        stats = await pool.fetchrow("""
            SELECT 
                ec.exchange_id as name,
                ec.display_name,
                ec.is_active,
                ec.deleted_at,
                
                -- 交易对数量
                (SELECT COUNT(*) FROM exchange_trading_pairs 
                 WHERE exchange_config_id = ec.id) as total_pairs,
                (SELECT COUNT(*) FROM exchange_trading_pairs 
                 WHERE exchange_config_id = ec.id AND is_enabled = true) as enabled_pairs,
                
                -- 策略数量
                (SELECT COUNT(*) FROM strategy_exchanges se
                 JOIN strategy_configs sc ON sc.id = se.strategy_id
                 WHERE se.exchange_config_id = ec.id AND sc.user_id = $2) as strategy_count,
                
                -- 订单统计
                (SELECT COUNT(*) FROM order_history oh
                 JOIN strategy_configs sc ON sc.id = oh.strategy_id
                 WHERE oh.exchange_id = ec.exchange_id AND sc.user_id = $2) as total_orders,
                (SELECT COUNT(*) FROM order_history oh
                 JOIN strategy_configs sc ON sc.id = oh.strategy_id
                 WHERE oh.exchange_id = ec.exchange_id AND oh.trading_mode = 'paper' AND sc.user_id = $2) as paper_orders,
                (SELECT COUNT(*) FROM order_history oh
                 JOIN strategy_configs sc ON sc.id = oh.strategy_id
                 WHERE oh.exchange_id = ec.exchange_id AND oh.trading_mode = 'live' AND sc.user_id = $2) as live_orders,
                
                -- 收益统计
                (SELECT COALESCE(SUM(pr.net_profit), 0) FROM pnl_records pr
                 JOIN strategy_configs sc ON sc.id = pr.strategy_id
                 WHERE pr.exchange_id = ec.exchange_id AND sc.user_id = $2) as total_profit,
                (SELECT COALESCE(SUM(pr.net_profit), 0) FROM pnl_records pr
                 JOIN strategy_configs sc ON sc.id = pr.strategy_id
                 WHERE pr.exchange_id = ec.exchange_id AND pr.trading_mode = 'paper' AND sc.user_id = $2) as paper_profit,
                (SELECT COALESCE(SUM(pr.net_profit), 0) FROM pnl_records pr
                 JOIN strategy_configs sc ON sc.id = pr.strategy_id
                 WHERE pr.exchange_id = ec.exchange_id AND pr.trading_mode = 'live' AND sc.user_id = $2) as live_profit
                
            FROM exchange_configs ec
            WHERE ec.id = $1 AND ec.user_id = $2
        """, exchange_id, user.id)
        
        if not stats:
            raise HTTPException(status_code=404, detail="交易所不存在")
        
        return dict(stats)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{exchange_id}/assets")
async def get_exchange_assets(exchange_id: UUID, user: CurrentUser = Depends(get_current_user)):
    """
    获取交易所账户资产（实盘）
    """
    pool = await get_pg_pool()

    async def _fetch_keys(use_decrypt: bool) -> Optional[dict]:
        if use_decrypt:
            row = await pool.fetchrow("""
                SELECT
                    id,
                    exchange_id,
                    display_name,
                    is_active,
                    deleted_at,
                    CASE
                        WHEN api_key_encrypted LIKE '\\x%' THEN pgp_sym_decrypt(decode(substr(api_key_encrypted, 3), 'hex'), 'inarbit_secret_key')
                        ELSE api_key_encrypted
                    END AS api_key,
                    CASE
                        WHEN api_secret_encrypted LIKE '\\x%' THEN pgp_sym_decrypt(decode(substr(api_secret_encrypted, 3), 'hex'), 'inarbit_secret_key')
                        ELSE api_secret_encrypted
                    END AS api_secret,
                    CASE
                        WHEN passphrase_encrypted LIKE '\\x%' THEN pgp_sym_decrypt(decode(substr(passphrase_encrypted, 3), 'hex'), 'inarbit_secret_key')
                        ELSE passphrase_encrypted
                    END AS passphrase
                FROM exchange_configs
                WHERE id = $1 AND user_id = $2
            """, exchange_id, user.id)
        else:
            row = await pool.fetchrow("""
                SELECT id, exchange_id, display_name, is_active, deleted_at,
                       api_key_encrypted AS api_key,
                       api_secret_encrypted AS api_secret,
                       passphrase_encrypted AS passphrase
                FROM exchange_configs
                WHERE id = $1 AND user_id = $2
            """, exchange_id, user.id)
        return dict(row) if row else None

    try:
        try:
            exchange = await _fetch_keys(True)
        except Exception:
            exchange = await _fetch_keys(False)

        if not exchange:
            raise HTTPException(status_code=404, detail="交易所不存在")

        if not exchange.get('is_active') or exchange.get('deleted_at'):
            raise HTTPException(status_code=400, detail="交易所已停用或删除")

        api_key = exchange.get('api_key')
        api_secret = exchange.get('api_secret')
        passphrase = exchange.get('passphrase')

        if not api_key or not api_secret:
            raise HTTPException(status_code=400, detail="交易所密钥缺失")

        client = CCXTExchange(exchange['exchange_id'], api_key=api_key, secret=api_secret, password=passphrase)

        try:
            balance = await client.fetch_balance()
            totals = balance.get('total') or {}
            free = balance.get('free') or {}
            used = balance.get('used') or {}

            assets = []
            symbols = []
            stable_coins = {'USDT', 'USDC', 'USD', 'BUSD'}

            for coin, total in totals.items():
                try:
                    total_val = float(total or 0)
                except Exception:
                    continue
                if total_val <= 0:
                    continue

                free_val = float(free.get(coin, 0) or 0)
                locked_val = float(used.get(coin, 0) or 0)
                price = 1.0 if coin in stable_coins else None
                if price is None:
                    symbols.append(f"{coin}/USDT")

                assets.append({
                    "coin": coin,
                    "free": free_val,
                    "locked": locked_val,
                    "total": total_val,
                    "price": price,
                    "value_usdt": total_val * price if price is not None else None
                })

            ticker_map = {}
            if symbols:
                try:
                    tickers = await client.fetch_tickers(symbols)
                    for symbol, ticker in (tickers or {}).items():
                        last = ticker.get('last') or ticker.get('close')
                        if last is not None:
                            ticker_map[symbol] = float(last)
                except Exception:
                    ticker_map = {}

            total_value = 0.0
            for asset in assets:
                if asset['price'] is None:
                    symbol = f"{asset['coin']}/USDT"
                    price = ticker_map.get(symbol)
                    if price is not None:
                        asset['price'] = price
                        asset['value_usdt'] = asset['total'] * price
                if asset.get('value_usdt') is not None:
                    total_value += float(asset['value_usdt'])

            assets.sort(key=lambda x: x.get('value_usdt') or 0, reverse=True)

            return {
                "exchange_id": str(exchange_id),
                "exchange_code": exchange['exchange_id'],
                "display_name": exchange.get('display_name'),
                "total_value_usdt": round(total_value, 6),
                "assets": assets,
            }
        finally:
            await client.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


