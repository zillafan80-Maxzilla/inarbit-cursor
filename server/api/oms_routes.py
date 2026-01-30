from typing import Optional
from datetime import datetime
import asyncio
import json
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth import CurrentUser, get_current_user, get_current_user_from_token
from ..services.oms_service import OmsService
from ..db import get_redis
from ..services.order_service import OrderService, PnLService

router = APIRouter(prefix="/api/v1/oms", tags=["oms"])


class ExecuteLatestRequest(BaseModel):
    trading_mode: str = Field("paper")
    confirm_live: bool = Field(False)
    idempotency_key: Optional[str] = Field(None)
    limit: int = Field(1, ge=1, le=10)


class ManageOrderRequest(BaseModel):
    trading_mode: str = Field("paper")
    confirm_live: bool = Field(False)


class ManagePlanRequest(BaseModel):
    trading_mode: str = Field("paper")
    confirm_live: bool = Field(False)
    limit: int = Field(20, ge=1, le=200)


class ManageReconcilePlanRequest(ManagePlanRequest):
    max_rounds: int = Field(5, ge=1, le=50)
    sleep_ms: int = Field(500, ge=0, le=60000)
    auto_cancel: bool = Field(False)
    max_age_seconds: Optional[int] = Field(None, ge=1, le=86400)


class ReconcilePreviewRequest(BaseModel):
    terminal: bool = Field(False)
    auto_cancel: bool = Field(False)
    timeout: bool = Field(False)
    max_rounds_exhausted: bool = Field(False)
    last_status_counts: Optional[dict[str, int]] = Field(None)


class ReconcilePreviewBatchRequest(BaseModel):
    cases: list[ReconcilePreviewRequest] = Field(..., min_length=1, max_length=200)


@router.post("/execute_latest")
async def execute_latest(req: ExecuteLatestRequest, user: CurrentUser = Depends(get_current_user)):
    oms = OmsService()
    try:
        result = await oms.execute_latest(
            user_id=user.id,
            trading_mode=req.trading_mode,
            confirm_live=req.confirm_live,
            idempotency_key=req.idempotency_key,
            limit=req.limit,
        )
        return jsonable_encoder({"success": True, "decision": result.decision, "orders": result.orders})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reconcile/preview/batch")
async def preview_reconcile_next_action_batch(
    req: ReconcilePreviewBatchRequest,
    user: CurrentUser = Depends(get_current_user),
):
    _ = user
    oms = OmsService()
    try:
        results = []
        for c in (req.cases or []):
            r = oms.preview_next_action(
                terminal=c.terminal,
                auto_cancel=c.auto_cancel,
                timeout=c.timeout,
                max_rounds_exhausted=c.max_rounds_exhausted,
                last_status_counts=c.last_status_counts,
            )
            results.append(r)
        return jsonable_encoder({"success": True, "results": results})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reconcile/preview")
async def preview_reconcile_next_action(
    req: ReconcilePreviewRequest,
    user: CurrentUser = Depends(get_current_user),
):
    _ = user
    oms = OmsService()
    try:
        result = oms.preview_next_action(
            terminal=req.terminal,
            auto_cancel=req.auto_cancel,
            timeout=req.timeout,
            max_rounds_exhausted=req.max_rounds_exhausted,
            last_status_counts=req.last_status_counts,
        )
        return jsonable_encoder({"success": True, **result} if isinstance(result, dict) else {"success": True, "result": result})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/alerts")
async def get_alert_history(
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(get_current_user),
):
    """获取 OMS 告警历史"""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit must be <= 500")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    redis = await get_redis()
    key = f"audit:alert:{user.id}"
    end = offset + limit - 1
    rows = await redis.lrange(key, offset, end)
    alerts = []
    for raw in rows or []:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")
        if isinstance(raw, str):
            try:
                alerts.append(json.loads(raw))
            except Exception:
                alerts.append({"message": raw})
        else:
            alerts.append({"message": str(raw)})

    total = await redis.llen(key)
    return {"success": True, "alerts": alerts, "total": total, "limit": limit, "offset": offset}


@router.post("/plans/{plan_id}/reconcile")
async def reconcile_oms_plan(
    plan_id: UUID,
    req: ManageReconcilePlanRequest,
    user: CurrentUser = Depends(get_current_user),
):
    oms = OmsService()
    try:
        result = await oms.reconcile_plan(
            user_id=user.id,
            plan_id=plan_id,
            trading_mode=req.trading_mode,
            confirm_live=req.confirm_live,
            limit=req.limit,
            max_rounds=req.max_rounds,
            sleep_ms=req.sleep_ms,
            auto_cancel=req.auto_cancel,
            max_age_seconds=req.max_age_seconds,
        )
        return jsonable_encoder({"success": True, **result} if isinstance(result, dict) else {"success": True, "result": result})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/plans/{plan_id}/cancel")
async def cancel_oms_plan(
    plan_id: UUID,
    req: ManagePlanRequest,
    user: CurrentUser = Depends(get_current_user),
):
    oms = OmsService()
    try:
        result = await oms.cancel_plan(
            user_id=user.id,
            plan_id=plan_id,
            trading_mode=req.trading_mode,
            confirm_live=req.confirm_live,
            limit=req.limit,
        )
        return jsonable_encoder({"success": True, **result} if isinstance(result, dict) else {"success": True, "result": result})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/plans/{plan_id}/refresh")
async def refresh_oms_plan(
    plan_id: UUID,
    req: ManagePlanRequest,
    user: CurrentUser = Depends(get_current_user),
):
    oms = OmsService()
    try:
        result = await oms.refresh_plan(
            user_id=user.id,
            plan_id=plan_id,
            trading_mode=req.trading_mode,
            confirm_live=req.confirm_live,
            limit=req.limit,
        )
        return jsonable_encoder({"success": True, **result} if isinstance(result, dict) else {"success": True, "result": result})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/refresh")
async def refresh_oms_order(
    order_id: UUID,
    req: ManageOrderRequest,
    user: CurrentUser = Depends(get_current_user),
):
    oms = OmsService()
    try:
        result = await oms.refresh_order(
            user_id=user.id,
            order_id=order_id,
            trading_mode=req.trading_mode,
            confirm_live=req.confirm_live,
        )
        return jsonable_encoder({"success": True, **result} if isinstance(result, dict) else {"success": True, "result": result})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/cancel")
async def cancel_oms_order(
    order_id: UUID,
    req: ManageOrderRequest,
    user: CurrentUser = Depends(get_current_user),
):
    oms = OmsService()
    try:
        result = await oms.cancel_order(
            user_id=user.id,
            order_id=order_id,
            trading_mode=req.trading_mode,
            confirm_live=req.confirm_live,
        )
        return jsonable_encoder({"success": True, **result} if isinstance(result, dict) else {"success": True, "result": result})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/plans/latest")
async def get_latest_plans(
    user: CurrentUser = Depends(get_current_user),
    trading_mode: str = "paper",
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 20,
):
    oms = OmsService()
    try:
        plans = await oms.get_execution_plans(
            user_id=user.id,
            trading_mode=trading_mode,
            status=status,
            kind=kind,
            limit=limit,
        )
        return jsonable_encoder({"success": True, "plans": plans})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/plans/{plan_id}")
async def get_oms_plan(
    plan_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    trading_mode: str = "paper",
):
    oms = OmsService()
    try:
        plan = await oms.get_execution_plan(user_id=user.id, plan_id=plan_id, trading_mode=trading_mode)
        if not plan:
            raise HTTPException(status_code=404, detail="plan not found")
        return jsonable_encoder({"success": True, "plan": plan})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/opportunities")
async def list_oms_opportunities(
    user: CurrentUser = Depends(get_current_user),
    trading_mode: str = "paper",
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 50,
):
    oms = OmsService()
    try:
        opportunities = await oms.get_opportunities(
            user_id=user.id,
            trading_mode=trading_mode,
            status=status,
            kind=kind,
            limit=limit,
        )
        return jsonable_encoder({"success": True, "opportunities": opportunities})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/opportunities/{opportunity_id}")
async def get_oms_opportunity(
    opportunity_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    trading_mode: str = "paper",
):
    oms = OmsService()
    try:
        opp = await oms.get_opportunity(
            user_id=user.id,
            opportunity_id=opportunity_id,
            trading_mode=trading_mode,
        )
        if not opp:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return jsonable_encoder({"success": True, "opportunity": opp})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orders")
async def list_oms_orders(
    user: CurrentUser = Depends(get_current_user),
    trading_mode: str = "paper",
    exchange_id: Optional[str] = None,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    account_type: Optional[str] = None,
    client_order_id: Optional[str] = None,
    plan_id: Optional[UUID] = None,
    leg_id: Optional[str] = None,
    external_order_id: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    try:
        def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
            if not raw:
                return None
            try:
                return datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except Exception:
                return None

        dt_after = _parse_dt(created_after)
        dt_before = _parse_dt(created_before)
        orders = await OrderService.get_orders(
            user_id=user.id,
            exchange_id=exchange_id,
            symbol=symbol,
            status=status,
            account_type=account_type,
            client_order_id=client_order_id,
            plan_id=plan_id,
            leg_id=leg_id,
            external_order_id=external_order_id,
            created_after=dt_after,
            created_before=dt_before,
            trading_mode=trading_mode,
            limit=limit,
            offset=offset,
        )
        return jsonable_encoder({"success": True, "orders": orders})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/fills")
async def list_oms_fills(
    user: CurrentUser = Depends(get_current_user),
    trading_mode: str = "paper",
    exchange_id: Optional[str] = None,
    account_type: Optional[str] = None,
    symbol: Optional[str] = None,
    order_id: Optional[UUID] = None,
    plan_id: Optional[UUID] = None,
    external_trade_id: Optional[str] = None,
    external_order_id: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    try:
        def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
            if not raw:
                return None
            try:
                return datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except Exception:
                return None

        dt_after = _parse_dt(created_after)
        dt_before = _parse_dt(created_before)
        order_ids = None
        if plan_id is not None:
            orders = await OrderService.get_orders(
                user_id=user.id,
                plan_id=plan_id,
                trading_mode=trading_mode,
                limit=1000,
            )
            order_ids = [o.get("id") for o in orders if o.get("id")]

        fills = await OrderService.get_fills(
            user_id=user.id,
            exchange_id=exchange_id,
            account_type=account_type,
            symbol=symbol,
            order_id=order_id,
            order_ids=order_ids,
            external_trade_id=external_trade_id,
            external_order_id=external_order_id,
            created_after=dt_after,
            created_before=dt_before,
            trading_mode=trading_mode,
            limit=limit,
            offset=offset,
        )
        return jsonable_encoder({"success": True, "fills": fills})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pnl/summary")
async def get_oms_pnl_summary(
    user: CurrentUser = Depends(get_current_user),
    trading_mode: str = "paper",
):
    try:
        stats = await PnLService.get_statistics(user_id=user.id, trading_mode=trading_mode)
        total_profit = await PnLService.get_total_profit(user_id=user.id, trading_mode=trading_mode)
        summary = {
            **stats,
            "total_profit": float(total_profit),
        }
        return jsonable_encoder({"success": True, "summary": summary})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pnl/history")
async def get_oms_pnl_history(
    user: CurrentUser = Depends(get_current_user),
    trading_mode: str = "paper",
    exchange_id: Optional[str] = None,
    symbol: Optional[str] = None,
    plan_id: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    try:
        def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
            if not raw:
                return None
            try:
                return datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except Exception:
                return None

        dt_after = _parse_dt(created_after)
        dt_before = _parse_dt(created_before)
        rows = await PnLService.get_history(
            user_id=user.id,
            trading_mode=trading_mode,
            exchange_id=exchange_id,
            symbol=symbol,
            plan_id=plan_id,
            created_after=dt_after,
            created_before=dt_before,
            limit=limit,
            offset=offset,
        )
        return jsonable_encoder({"success": True, "history": rows})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pnl/stream")
async def stream_oms_pnl(
    request: Request,
    trading_mode: str = "paper",
    exchange_id: Optional[str] = None,
    symbol: Optional[str] = None,
    plan_id: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    interval: float = 2.0,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    try:
        user = await get_current_user_from_token(token) if token else await get_current_user(authorization)

        def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
            if not raw:
                return None
            try:
                return datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except Exception:
                return None

        dt_after = _parse_dt(created_after)
        dt_before = _parse_dt(created_before)
        sleep_seconds = max(0.5, float(interval or 2.0))

        async def _event_stream():
            while True:
                if await request.is_disconnected():
                    break
                stats = await PnLService.get_statistics(user_id=user.id, trading_mode=trading_mode)
                total_profit = await PnLService.get_total_profit(user_id=user.id, trading_mode=trading_mode)
                summary = {
                    **(stats or {}),
                    "total_profit": float(total_profit),
                }
                rows = await PnLService.get_history(
                    user_id=user.id,
                    trading_mode=trading_mode,
                    exchange_id=exchange_id,
                    symbol=symbol,
                    plan_id=plan_id,
                    created_after=dt_after,
                    created_before=dt_before,
                    limit=limit,
                    offset=offset,
                )
                payload = {
                    "summary": summary,
                    "history": rows,
                    "timestamp": int(time.time() * 1000),
                }
                data = json.dumps(payload, ensure_ascii=False, default=str)
                yield f"data: {data}\n\n"
                await asyncio.sleep(sleep_seconds)

        return StreamingResponse(_event_stream(), media_type="text/event-stream")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
