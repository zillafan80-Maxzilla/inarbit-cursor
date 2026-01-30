"""
行情数据 API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List

from ..auth import CurrentUser, get_current_user
from ..exchange.ccxt_exchange import CCXTExchange
from ..exchange.binance_connector import apply_binance_base_url, get_binance_base_url

router = APIRouter(prefix="/market", tags=["Market"])


@router.get("/ohlcv")
async def get_ohlcv(
    exchange_id: str = Query(..., description="交易所 ID，例如 binance"),
    symbol: str = Query(..., description="交易对，例如 BSW/USDT"),
    timeframe: str = Query("1h", description="K 线周期，例如 1m/5m/1h/1d"),
    limit: int = Query(200, ge=1, le=1000),
    user: CurrentUser = Depends(get_current_user),
):
    """获取交易所 K 线（OHLCV）"""
    try:
        exchange = CCXTExchange(exchange_id)
        if exchange_id.lower() == "binance":
            base_url = await get_binance_base_url()
            apply_binance_base_url(exchange.client, base_url)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Unsupported exchange: {exchange_id}")

    try:
        rows = await exchange.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        items = [
            {
                "timestamp": r[0],
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
            }
            for r in rows or []
        ]
        return {
            "exchange_id": exchange_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "items": items,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            await exchange.close()
        except Exception:
            pass
