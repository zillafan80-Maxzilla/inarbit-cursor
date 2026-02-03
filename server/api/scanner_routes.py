"""
机会/扫描器运行时配置 API

用于在不重启服务的情况下，动态调整机会扫描器参数（triangular/cashcarry）。
这在生产环境进行“真实行情+成本”的模拟盘压测/调参时非常有用。

注意：接口仅管理员可用（require_admin）。
"""

from __future__ import annotations

from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_admin
from ..db import get_redis
from ..services import ServiceContainer


router = APIRouter(prefix="/api/v1/scanners", tags=["V1 - Scanners"])


class TriangularScannerUpdate(BaseModel):
    exchange_id: Optional[str] = Field(None, description="ccxt exchange id, e.g. binance/okx")
    base_currency: Optional[str] = Field(None, description="base currency for triangles, e.g. USDT")
    min_profit_rate: Optional[float] = Field(None, description="keep opportunities with profit_rate >= this value")
    fee_rate: Optional[float] = Field(None, ge=0.0, le=0.01, description="fee rate used in profit estimate")
    refresh_interval_seconds: Optional[float] = Field(None, ge=0.2, le=60.0)
    ttl_seconds: Optional[int] = Field(None, ge=1, le=3600)
    max_opportunities: Optional[int] = Field(None, ge=1, le=1000)


class CashCarryScannerUpdate(BaseModel):
    exchange_id: Optional[str] = Field(None, description="ccxt exchange id, e.g. binance/okx")
    quote_currency: Optional[str] = Field(None, description="quote currency for spot/perp, e.g. USDT")
    min_profit_rate: Optional[float] = Field(None, description="keep opportunities with profit_rate >= this value")
    spot_fee_rate: Optional[float] = Field(None, ge=0.0, le=0.01)
    perp_fee_rate: Optional[float] = Field(None, ge=0.0, le=0.01)
    funding_horizon_intervals: Optional[int] = Field(None, ge=1, le=48)
    refresh_interval_seconds: Optional[float] = Field(None, ge=0.2, le=60.0)
    ttl_seconds: Optional[int] = Field(None, ge=1, le=3600)
    max_opportunities: Optional[int] = Field(None, ge=1, le=1000)


def _decode_redis_hash(raw: dict[Any, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (raw or {}).items():
        if isinstance(k, (bytes, bytearray)):
            k = k.decode("utf-8", errors="ignore")
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("utf-8", errors="ignore")
        out[str(k)] = v
    return out


@router.get("/status")
async def get_scanners_status(user: CurrentUser = Depends(require_admin)) -> dict:
    _ = user
    tri = ServiceContainer.get_triangular_opportunity_service()
    cc = ServiceContainer.get_cashcarry_opportunity_service()

    redis = await get_redis()
    tri_metrics = _decode_redis_hash(await redis.hgetall("metrics:triangular_service"))
    cc_metrics = _decode_redis_hash(await redis.hgetall("metrics:cashcarry_service"))

    return {
        "success": True,
        "triangular": {
            "exchange_id": getattr(tri, "exchange_id", None),
            "base_currency": getattr(tri, "base_currency", None),
            "min_profit_rate": getattr(tri, "min_profit_rate", None),
            "fee_rate": getattr(tri, "fee_rate", None),
            "refresh_interval_seconds": getattr(tri, "refresh_interval_seconds", None),
            "ttl_seconds": getattr(tri, "ttl_seconds", None),
            "max_opportunities": getattr(tri, "max_opportunities", None),
            "metrics": tri_metrics,
        },
        "cashcarry": {
            "exchange_id": getattr(cc, "exchange_id", None),
            "quote_currency": getattr(cc, "quote_currency", None),
            "min_profit_rate": getattr(cc, "min_profit_rate", None),
            "spot_fee_rate": getattr(cc, "spot_fee_rate", None),
            "perp_fee_rate": getattr(cc, "perp_fee_rate", None),
            "funding_horizon_intervals": getattr(cc, "funding_horizon_intervals", None),
            "refresh_interval_seconds": getattr(cc, "refresh_interval_seconds", None),
            "ttl_seconds": getattr(cc, "ttl_seconds", None),
            "max_opportunities": getattr(cc, "max_opportunities", None),
            "metrics": cc_metrics,
        },
    }


@router.put("/triangular")
async def update_triangular_scanner(
    payload: TriangularScannerUpdate,
    user: CurrentUser = Depends(require_admin),
) -> dict:
    _ = user
    tri = ServiceContainer.get_triangular_opportunity_service()

    updated: dict[str, Any] = {}
    for field in (
        "exchange_id",
        "base_currency",
        "min_profit_rate",
        "fee_rate",
        "refresh_interval_seconds",
        "ttl_seconds",
        "max_opportunities",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(tri, field, value)
            updated[field] = value

    if not updated:
        raise HTTPException(status_code=400, detail="No fields to update")

    return {"success": True, "updated": updated}


@router.put("/cashcarry")
async def update_cashcarry_scanner(
    payload: CashCarryScannerUpdate,
    user: CurrentUser = Depends(require_admin),
) -> dict:
    _ = user
    cc = ServiceContainer.get_cashcarry_opportunity_service()

    updated: dict[str, Any] = {}
    for field in (
        "exchange_id",
        "quote_currency",
        "min_profit_rate",
        "spot_fee_rate",
        "perp_fee_rate",
        "funding_horizon_intervals",
        "refresh_interval_seconds",
        "ttl_seconds",
        "max_opportunities",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(cc, field, value)
            updated[field] = value

    if not updated:
        raise HTTPException(status_code=400, detail="No fields to update")

    return {"success": True, "updated": updated}

