import asyncio
import json
import hashlib
import os
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import ccxt.async_support as ccxt

from ..db import get_pg_pool
from ..db import get_redis
from .market_data_repository import MarketDataRepository
from .config_service import get_config_service
from .order_service import OrderService, PnLService
from ..risk_manager import RiskManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OmsExecutionResult:
    decision: dict
    orders: list[dict]


class OmsService:
    def __init__(
        self,
        exchange_id: str = "binance",
        spot_fee_rate: Decimal = Decimal("0.0004"),
        perp_fee_rate: Decimal = Decimal("0.0004"),
    ):
        self.exchange_id = exchange_id
        self.spot_fee_rate = spot_fee_rate
        self.perp_fee_rate = perp_fee_rate
        self._repo = MarketDataRepository()

    async def get_execution_plan(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        trading_mode: str = "paper",
    ) -> Optional[dict[str, Any]]:
        if trading_mode not in {"paper", "live"}:
            raise ValueError("invalid trading_mode")

        table_name = 'paper_execution_plans' if trading_mode == 'paper' else 'live_execution_plans'
        pool = await get_pg_pool()

        row = await pool.fetchrow(
            f"""
            SELECT *
            FROM {table_name}
            WHERE id = $1 AND user_id = $2
            """,
            plan_id,
            user_id,
        )
        if not row:
            return None

        plan = dict(row)
        legs = plan.get("legs")
        if isinstance(legs, str):
            try:
                legs = json.loads(legs)
            except Exception:
                legs = []
        if not isinstance(legs, list):
            legs = []
        plan["legs"] = legs
        return plan

    async def get_execution_plans(
        self,
        *,
        user_id: UUID,
        trading_mode: str = "paper",
        status: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if trading_mode not in {"paper", "live"}:
            raise ValueError("invalid trading_mode")

        table_name = 'paper_execution_plans' if trading_mode == 'paper' else 'live_execution_plans'
        pool = await get_pg_pool()

        where_clauses = ["user_id = $1"]
        params: list[Any] = [user_id]
        param_idx = 2

        if status:
            where_clauses.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if kind:
            where_clauses.append(f"kind = ${param_idx}")
            params.append(kind)
            param_idx += 1

        where_clause = f"WHERE {' AND '.join(where_clauses)}"
        query = f"""
            SELECT *
            FROM {table_name}
            {where_clause}
            ORDER BY created_at DESC
            LIMIT {limit}
        """

        rows = await pool.fetch(query, *params)
        return [dict(r) for r in rows]

    async def execute_latest(
        self,
        *,
        user_id: UUID,
        trading_mode: str = "paper",
        confirm_live: bool = False,
        idempotency_key: Optional[str] = None,
        limit: int = 1,
    ) -> OmsExecutionResult:
        if trading_mode not in {"paper", "live"}:
            raise ValueError("invalid trading_mode")

        if trading_mode == "live" and not confirm_live:
            raise PermissionError("live mode requires confirm_live=true")

        if trading_mode == "live" and os.getenv("INARBIT_ENABLE_LIVE_OMS", "0").strip() not in {"1", "true", "True"}:
            raise PermissionError("live mode requires INARBIT_ENABLE_LIVE_OMS=1")

        redis = await get_redis()
        if idempotency_key:
            dedupe_key = f"oms:dedupe:{user_id}:{idempotency_key}"
            cached = await redis.get(dedupe_key)
            if cached:
                payload = json.loads(cached)
                return OmsExecutionResult(decision=payload["decision"], orders=payload["orders"])

        decision = await self._get_latest_decision(user_id=user_id, limit=limit)
        strategy_type = decision.get("strategyType") or decision.get("strategy_type")

        if os.getenv("INARBIT_ENABLE_RISK_CHECK", "0").strip() in {"1", "true", "True"}:
            risk_manager = RiskManager(user_id=str(user_id))
            allowed = await risk_manager.check()
            if not allowed:
                raise PermissionError("risk check failed")

        plan_kind = "basis" if strategy_type == "cashcarry" else ("triangle" if strategy_type == "triangular" else "unknown")
        plan_id = await self._create_execution_plan(user_id=user_id, trading_mode=trading_mode, kind=plan_kind)

        try:
            if strategy_type == "cashcarry":
                result = await self._execute_cashcarry(user_id=user_id, decision=decision, trading_mode=trading_mode, plan_id=plan_id)
            elif strategy_type == "triangular":
                result = await self._execute_triangular(user_id=user_id, decision=decision, trading_mode=trading_mode, plan_id=plan_id)
            else:
                raise ValueError("unsupported strategy_type")
            await self._set_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode, legs=result.orders)

            post_poll_enabled = os.getenv("OMS_POST_EXEC_POLL_ENABLED", "0").strip() in {"1", "true", "True"}
            post_poll_max_rounds = 0
            post_poll_sleep_ms = 0
            post_poll_limit = 200
            try:
                post_poll_max_rounds = int(os.getenv("OMS_POST_EXEC_POLL_MAX_ROUNDS", "5").strip() or "5")
            except Exception:
                post_poll_max_rounds = 5
            try:
                post_poll_sleep_ms = int(os.getenv("OMS_POST_EXEC_POLL_SLEEP_MS", "500").strip() or "500")
            except Exception:
                post_poll_sleep_ms = 500
            try:
                post_poll_limit = int(os.getenv("OMS_POST_EXEC_POLL_LIMIT", "200").strip() or "200")
            except Exception:
                post_poll_limit = 200

            def _is_terminal(st: Optional[str]) -> bool:
                if not st:
                    return False
                return st in {"filled", "cancelled", "rejected"}

            orders_now = await OrderService.get_orders(user_id=user_id, plan_id=plan_id, trading_mode=trading_mode, limit=post_poll_limit)
            if not isinstance(orders_now, list):
                orders_now = []

            terminal_now = all(_is_terminal((o or {}).get("status")) for o in orders_now)
            rejected_now = any(((o or {}).get("status") == "rejected") for o in orders_now)

            poll_summary: Optional[dict[str, Any]] = None
            if trading_mode == "live" and post_poll_enabled and (not terminal_now) and post_poll_max_rounds > 0:
                polled = await self._poll_plan_orders_until_terminal(
                    user_id=user_id,
                    plan_id=plan_id,
                    trading_mode=trading_mode,
                    confirm_live=confirm_live,
                    limit=max(1, post_poll_limit),
                    max_rounds=max(1, post_poll_max_rounds),
                    sleep_ms=max(0, post_poll_sleep_ms),
                )
                if isinstance(polled, dict):
                    poll_summary = polled.get("summary") if isinstance(polled.get("summary"), dict) else None
                    last_payload = polled.get("last") if isinstance(polled.get("last"), dict) else None
                    if isinstance(last_payload, dict) and isinstance(last_payload.get("orders"), list):
                        orders_now = last_payload.get("orders")
                        terminal_now = all(_is_terminal((o or {}).get("status")) for o in orders_now)
                        rejected_now = any(((o or {}).get("status") == "rejected") for o in orders_now)

                try:
                    legs_payload = await self._get_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode)
                    if not isinstance(legs_payload, list):
                        legs_payload = []
                    legs_payload.append({"kind": "post_exec_poll_summary", "summary": (poll_summary or polled)})
                    await self._set_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode, legs=legs_payload)
                except Exception:
                    pass

            status_to_set = "running"
            error_message: Optional[str] = None
            if terminal_now:
                if rejected_now:
                    status_to_set = "failed"
                    error_message = "rejected"
                else:
                    status_to_set = "completed"
            elif trading_mode == "paper":
                status_to_set = "completed"

            await self._update_execution_plan(plan_id=plan_id, trading_mode=trading_mode, status=status_to_set, error_message=error_message)

            if status_to_set == "completed":
                try:
                    await self._record_plan_pnl(
                        user_id=user_id,
                        plan_id=plan_id,
                        trading_mode=trading_mode,
                        kind=plan_kind,
                    )
                except Exception:
                    pass

            try:
                await self._publish_log(
                    user_id=str(user_id),
                    level="INFO" if status_to_set in {"completed", "running"} else "WARN",
                    message=f"OMS plan {plan_id} status={status_to_set}",
                )
            except Exception:
                pass

            try:
                metrics_key = "metrics:oms_service"
                await redis.hset(
                    metrics_key,
                    mapping={
                        "last_plan_id": str(plan_id),
                        "last_trading_mode": trading_mode,
                        "last_status": status_to_set,
                        "last_error": error_message or "",
                        "timestamp_ms": str(int(time.time() * 1000)),
                    },
                )
                await redis.expire(metrics_key, 300)
            except Exception:
                pass

            try:
                orders = await OrderService.get_orders(user_id=user_id, plan_id=plan_id, trading_mode=trading_mode, limit=200)
                status_counts: dict[str, int] = {}
                if isinstance(orders, list):
                    for o in orders:
                        if not isinstance(o, dict):
                            continue
                        st = o.get("status") or "unknown"
                        status_counts[str(st)] = status_counts.get(str(st), 0) + 1
                total_orders = sum(status_counts.values())
                terminal_count = int(status_counts.get("filled") or 0) + int(status_counts.get("cancelled") or 0) + int(status_counts.get("rejected") or 0)
                non_terminal_count = max(0, total_orders - terminal_count)

                legs_payload = await self._get_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode)
                if not isinstance(legs_payload, list):
                    legs_payload = []
                legs_payload.append(
                    {
                        "kind": "execution_summary",
                        "plan_id": str(plan_id),
                        "trading_mode": trading_mode,
                        "status_counts": status_counts,
                        "orders_summary": {
                            "total": total_orders,
                            "terminal": terminal_count,
                            "non_terminal": non_terminal_count,
                        },
                        "reconcile_suggested_request": self._get_default_reconcile_suggested_request(
                            plan_id=plan_id,
                            trading_mode=trading_mode,
                            confirm_live=confirm_live,
                        ),
                    }
                )
                await self._set_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode, legs=legs_payload)
            except Exception:
                pass
        except Exception as e:
            try:
                compensate_enabled = os.getenv("OMS_FAILURE_COMPENSATE_CANCEL_ENABLED", "0").strip() in {"1", "true", "True"}
                if compensate_enabled and trading_mode == "live":
                    stats = {"total": 0, "ok": 0, "skipped": 0, "failed": 0}
                    results: list[dict[str, Any]] = []

                    orders_for_cancel = await OrderService.get_orders(user_id=user_id, plan_id=plan_id, trading_mode=trading_mode, limit=200)
                    if not isinstance(orders_for_cancel, list):
                        orders_for_cancel = []
                    for o in orders_for_cancel:
                        oid = (o or {}).get("id") if isinstance(o, dict) else None
                        if not oid:
                            continue
                        stats["total"] += 1
                        if (o.get("status") in {"filled", "cancelled", "rejected"}):
                            stats["ok"] += 1
                            stats["skipped"] += 1
                            results.append({"order_id": str(oid), "ok": True, "skipped": True})
                            continue
                        try:
                            await self.cancel_order(user_id=user_id, order_id=oid, trading_mode=trading_mode, confirm_live=confirm_live)
                            stats["ok"] += 1
                            results.append({"order_id": str(oid), "ok": True})
                        except Exception as ce:
                            stats["failed"] += 1
                            results.append({"order_id": str(oid), "ok": False, "error": str(ce)})

                    try:
                        legs_payload = await self._get_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode)
                        if not isinstance(legs_payload, list):
                            legs_payload = []
                        legs_payload.append({"kind": "failure_compensation", "summary": {"action": "best_effort_cancel", "stats": stats, "results": results}})
                        await self._set_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode, legs=legs_payload)
                    except Exception:
                        pass
                elif trading_mode != "live" and post_poll_enabled:
                    logger.info("OMS post-exec polling skipped for non-live trading mode")
            except Exception:
                pass

            try:
                if 'result' in locals() and isinstance(result, OmsExecutionResult):
                    await self._set_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode, legs=result.orders)
            except Exception:
                pass
            try:
                legs_payload: list[dict[str, Any]] = []
                if 'result' in locals() and isinstance(result, OmsExecutionResult) and isinstance(result.orders, list):
                    legs_payload = list(result.orders)
                else:
                    legs_payload = await self._get_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode)
                    if not isinstance(legs_payload, list):
                        legs_payload = []

                legs_payload.append(
                    {
                        "kind": "reconcile_suggested_request",
                        "request": self._get_default_reconcile_suggested_request(
                            plan_id=plan_id,
                            trading_mode=trading_mode,
                            confirm_live=confirm_live,
                        ),
                        "error": str(e),
                    }
                )
                await self._set_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode, legs=legs_payload)
            except Exception:
                pass
            await self._update_execution_plan(plan_id=plan_id, trading_mode=trading_mode, status="failed", error_message=str(e))
            raise

        if idempotency_key:
            dedupe_key = f"oms:dedupe:{user_id}:{idempotency_key}"
            try:
                ttl = int(os.getenv("OMS_DEDUPE_TTL", "60").strip() or "60")
            except Exception:
                ttl = 60
            await redis.set(
                dedupe_key,
                json.dumps({"decision": result.decision, "orders": result.orders}, ensure_ascii=False),
                ex=max(10, ttl),
            )

        return result

    async def _publish_log(self, *, user_id: str, level: str, message: str) -> None:
        redis = await get_redis()
        await redis.publish(
            f"log:{user_id}:{level.lower()}",
            json.dumps(
                {
                    "level": level,
                    "source": "oms",
                    "message": message,
                },
                ensure_ascii=False,
            ),
        )

    async def _publish_order_update(self, *, user_id: str, order_id: str, status: str, data: dict) -> None:
        redis = await get_redis()
        await redis.publish(
            f"order:{user_id}:{status}",
            json.dumps(
                {
                    "order_id": order_id,
                    "status": status,
                    **(data or {}),
                },
                default=str,
                ensure_ascii=False,
            ),
        )

    async def _update_order_status(
        self,
        *,
        user_id: UUID,
        trading_mode: str,
        order_id: UUID,
        status: str,
        filled_quantity: Optional[Decimal] = None,
        average_price: Optional[Decimal] = None,
        fee: Optional[Decimal] = None,
        fee_currency: Optional[str] = None,
        external_order_id: Optional[str] = None,
    ) -> bool:
        ok = await OrderService.update_order_status(
            order_id=order_id,
            status=status,
            filled_quantity=filled_quantity,
            average_price=average_price,
            fee=fee,
            fee_currency=fee_currency,
            external_order_id=external_order_id,
            trading_mode=trading_mode,
        )
        detail = None
        try:
            detail_flag = (os.getenv("OMS_PUBLISH_ORDER_DETAIL", "0") or "0").strip().lower()
            if detail_flag in {"1", "true", "yes", "y"}:
                detail = await OrderService.get_order_by_id(order_id=order_id, trading_mode=trading_mode)
        except Exception:
            detail = None
        try:
            detail_payload = {}
            if detail:
                detail_payload = {
                    "plan_id": str(detail.get("plan_id")) if detail.get("plan_id") else None,
                    "leg_id": detail.get("leg_id"),
                    "symbol": detail.get("symbol"),
                    "side": detail.get("side"),
                    "order_type": detail.get("order_type"),
                    "quantity": str(detail.get("quantity")) if detail.get("quantity") is not None else None,
                    "price": str(detail.get("price")) if detail.get("price") is not None else None,
                    "account_type": detail.get("account_type"),
                    "exchange_id": detail.get("exchange_id"),
                }
            await self._publish_order_update(
                user_id=str(user_id),
                order_id=str(order_id),
                status=status,
                data={
                    "trading_mode": trading_mode,
                    "average_price": str(average_price) if average_price is not None else None,
                    "filled_quantity": str(filled_quantity) if filled_quantity is not None else None,
                    "fee": str(fee) if fee is not None else None,
                    "fee_currency": fee_currency,
                    "external_order_id": external_order_id,
                    **detail_payload,
                },
            )
        except Exception:
            pass
        return ok

    async def _poll_plan_orders_until_terminal(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        trading_mode: str,
        confirm_live: bool,
        limit: int,
        max_rounds: int,
        sleep_ms: int,
    ) -> dict[str, Any]:
        def _is_terminal(st: Optional[str]) -> bool:
            if not st:
                return False
            return st in {"filled", "cancelled", "rejected"}

        rounds_summary: list[dict[str, Any]] = []
        last: Optional[dict[str, Any]] = None
        terminal = False
        rejected = False
        last_status_counts: dict[str, int] = {}

        for i in range(max(1, max_rounds)):
            if i > 0 and sleep_ms:
                await asyncio.sleep(max(0, sleep_ms) / 1000.0)

            last = await self.refresh_plan(
                user_id=user_id,
                plan_id=plan_id,
                trading_mode=trading_mode,
                confirm_live=confirm_live,
                limit=limit,
            )
            orders = (last or {}).get("orders") if isinstance(last, dict) else []
            if not isinstance(orders, list):
                orders = []
            counts: dict[str, int] = {}
            for o in orders:
                if not isinstance(o, dict):
                    continue
                st = o.get("status") or "unknown"
                counts[str(st)] = counts.get(str(st), 0) + 1
            last_status_counts = counts
            terminal = all(_is_terminal((o or {}).get("status")) for o in orders)
            rejected = any(((o or {}).get("status") == "rejected") for o in orders)

            rounds_summary.append({"round": i + 1, "status_counts": counts, "terminal": terminal, "rejected": rejected})
            if terminal:
                break

        total_orders = 0
        for v in last_status_counts.values():
            try:
                total_orders += int(v)
            except Exception:
                continue
        terminal_count = int(last_status_counts.get("filled") or 0) + int(last_status_counts.get("cancelled") or 0) + int(last_status_counts.get("rejected") or 0)
        non_terminal_count = max(0, total_orders - terminal_count)

        summary: dict[str, Any] = {
            "plan_id": str(plan_id),
            "terminal": terminal,
            "rejected": rejected,
            "rounds": len(rounds_summary),
            "max_rounds": int(max_rounds),
            "sleep_ms": int(sleep_ms),
            "last_status_counts": last_status_counts,
            "orders_summary": {"total": total_orders, "terminal": terminal_count, "non_terminal": non_terminal_count, "status_counts": last_status_counts},
        }
        if not terminal:
            summary["reason"] = f"max_rounds_exhausted (max_rounds={max_rounds}, rounds={len(rounds_summary)})"
        elif rejected:
            summary["reason"] = "rejected"

        return {"last": last, "rounds": rounds_summary, "summary": summary}

    def _get_default_reconcile_suggested_request(
        self,
        *,
        plan_id: UUID,
        trading_mode: str,
        confirm_live: bool,
    ) -> dict[str, Any]:
        return self._build_reconcile_suggested_request(
            plan_id=plan_id,
            trading_mode=trading_mode,
            confirm_live=confirm_live,
            limit=None,
            max_rounds=None,
            sleep_ms=None,
            auto_cancel=False,
            max_age_seconds=None,
            apply_env_defaults=True,
            override_if_default_value=False,
        )

    def _build_reconcile_suggested_request(
        self,
        *,
        plan_id: UUID,
        trading_mode: str,
        confirm_live: bool,
        limit: Optional[int],
        max_rounds: Optional[int],
        sleep_ms: Optional[int],
        auto_cancel: Optional[bool],
        max_age_seconds: Optional[int],
        apply_env_defaults: bool,
        override_if_default_value: bool,
    ) -> dict[str, Any]:
        suggested_limit = 20 if limit is None else int(limit)
        suggested_max_rounds = 5 if max_rounds is None else int(max_rounds)
        suggested_sleep_ms = 500 if sleep_ms is None else int(sleep_ms)
        suggested_max_age_seconds: Optional[int] = max_age_seconds
        suggested_auto_cancel = False if auto_cancel is None else bool(auto_cancel)

        if apply_env_defaults:
            try:
                env_limit = int(os.getenv("OMS_RECONCILE_DEFAULT_LIMIT", "20").strip() or "20")
                if override_if_default_value or suggested_limit == 20:
                    suggested_limit = env_limit
            except Exception:
                pass
            try:
                env_max_rounds = int(os.getenv("OMS_RECONCILE_DEFAULT_MAX_ROUNDS", "5").strip() or "5")
                if override_if_default_value or suggested_max_rounds == 5:
                    suggested_max_rounds = env_max_rounds
            except Exception:
                pass
            try:
                env_sleep_ms = int(os.getenv("OMS_RECONCILE_DEFAULT_SLEEP_MS", "500").strip() or "500")
                if override_if_default_value or suggested_sleep_ms == 500:
                    suggested_sleep_ms = env_sleep_ms
            except Exception:
                pass

            if suggested_max_age_seconds is None:
                raw_max_age = os.getenv("OMS_RECONCILE_DEFAULT_MAX_AGE_SECONDS")
                if raw_max_age is not None and raw_max_age.strip() != "":
                    try:
                        suggested_max_age_seconds = int(raw_max_age.strip())
                    except Exception:
                        suggested_max_age_seconds = None

            if auto_cancel is None:
                raw_auto_cancel = os.getenv("OMS_RECONCILE_DEFAULT_AUTO_CANCEL", "0").strip()
                suggested_auto_cancel = raw_auto_cancel in {"1", "true", "True"}

        return {
            "plan_id": str(plan_id),
            "trading_mode": trading_mode,
            "confirm_live": bool(confirm_live),
            "limit": max(1, suggested_limit),
            "max_rounds": max(1, suggested_max_rounds),
            "sleep_ms": max(0, suggested_sleep_ms),
            "auto_cancel": bool(suggested_auto_cancel),
            "max_age_seconds": suggested_max_age_seconds,
        }

    async def refresh_order(
        self,
        *,
        user_id: UUID,
        order_id: UUID,
        trading_mode: str = "paper",
        confirm_live: bool = False,
    ) -> dict[str, Any]:
        if trading_mode not in {"paper", "live"}:
            raise ValueError("invalid trading_mode")

        if trading_mode == "live":
            self._require_live_enabled(confirm_live=confirm_live)

        order = await OrderService.get_order_by_id(order_id=order_id, trading_mode=trading_mode)
        if not order:
            raise ValueError("order not found")
        if str(order.get("user_id")) != str(user_id):
            raise PermissionError("order does not belong to user")

        if trading_mode == "paper":
            return order

        external_order_id = order.get("external_order_id")
        if not external_order_id:
            raise ValueError("missing external_order_id")

        account_type = order.get("account_type") or ((order.get("metadata") or {}).get("account_type") if isinstance(order.get("metadata"), dict) else None) or "spot"
        symbol = order.get("symbol")
        if not symbol:
            raise ValueError("missing symbol")

        ccxt_order = await self._fetch_live_order(account_type=account_type, symbol=symbol, external_order_id=str(external_order_id))
        exec_result = self._extract_exec_from_ccxt_order(ccxt_order, quantity_fallback=float(order.get("quantity") or 0))

        await self._update_order_status(
            user_id=user_id,
            order_id=order_id,
            status=exec_result["status"],
            filled_quantity=exec_result["filled_quantity"],
            average_price=exec_result["average_price"],
            fee=exec_result["fee"],
            fee_currency=exec_result.get("fee_currency"),
            external_order_id=exec_result.get("external_order_id"),
            trading_mode=trading_mode,
        )

        fills = exec_result.get("fills") or []
        for f in fills:
            ext_trade_id = f.get("external_trade_id")
            if ext_trade_id and await OrderService.fill_exists(ext_trade_id, trading_mode=trading_mode):
                continue
            if not ext_trade_id:
                continue
            await OrderService.create_fill(
                user_id=user_id,
                order_id=order_id,
                exchange_id=self.exchange_id,
                account_type=account_type,
                symbol=symbol,
                price=f["price"],
                quantity=f["quantity"],
                fee=f.get("fee"),
                fee_currency=f.get("fee_currency"),
                external_trade_id=ext_trade_id,
                external_order_id=exec_result.get("external_order_id"),
                raw=f.get("raw") or exec_result.get("raw"),
                trading_mode=trading_mode,
            )

        updated = await OrderService.get_order_by_id(order_id=order_id, trading_mode=trading_mode)
        return {"order": updated, "execution": exec_result}

    async def cancel_order(
        self,
        *,
        user_id: UUID,
        order_id: UUID,
        trading_mode: str = "paper",
        confirm_live: bool = False,
    ) -> dict[str, Any]:
        if trading_mode not in {"paper", "live"}:
            raise ValueError("invalid trading_mode")

        if trading_mode == "live":
            self._require_live_enabled(confirm_live=confirm_live)

        order = await OrderService.get_order_by_id(order_id=order_id, trading_mode=trading_mode)
        if not order:
            raise ValueError("order not found")
        if str(order.get("user_id")) != str(user_id):
            raise PermissionError("order does not belong to user")

        if trading_mode == "paper":
            await self._update_order_status(
                user_id=user_id,
                order_id=order_id,
                status="cancelled",
                trading_mode=trading_mode,
            )
            updated = await OrderService.get_order_by_id(order_id=order_id, trading_mode=trading_mode)
            return {"order": updated}

        external_order_id = order.get("external_order_id")
        if not external_order_id:
            raise ValueError("missing external_order_id")

        account_type = order.get("account_type") or ((order.get("metadata") or {}).get("account_type") if isinstance(order.get("metadata"), dict) else None) or "spot"
        symbol = order.get("symbol")
        if not symbol:
            raise ValueError("missing symbol")

        await self._cancel_live_order(account_type=account_type, symbol=symbol, external_order_id=str(external_order_id))
        return await self.refresh_order(user_id=user_id, order_id=order_id, trading_mode=trading_mode, confirm_live=confirm_live)

    async def refresh_plan(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        trading_mode: str = "paper",
        confirm_live: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        if trading_mode not in {"paper", "live"}:
            raise ValueError("invalid trading_mode")

        if trading_mode == "live":
            self._require_live_enabled(confirm_live=confirm_live)

        orders = await OrderService.get_orders(user_id=user_id, plan_id=plan_id, trading_mode=trading_mode, limit=limit)
        if trading_mode == "paper":
            stats = {"total": 0, "ok": 0, "skipped": 0, "failed": 0}
            for o in orders:
                oid = (o or {}).get("id") if isinstance(o, dict) else None
                if not oid:
                    continue
                stats["total"] += 1
                stats["ok"] += 1
            return {"orders": orders, "results": [], "stats": stats}

        terminal_statuses = {"filled", "cancelled", "rejected"}

        results: list[dict[str, Any]] = []
        refreshed: list[dict[str, Any]] = []
        stats = {"total": 0, "ok": 0, "skipped": 0, "failed": 0}
        for o in orders:
            oid = o.get("id")
            if not oid:
                continue
            if (o.get("status") in terminal_statuses):
                results.append({"order_id": str(oid), "ok": True, "skipped": True})
                refreshed.append(o)
                stats["ok"] += 1
                stats["skipped"] += 1
                continue
            try:
                r = await self.refresh_order(
                    user_id=user_id,
                    order_id=oid,
                    trading_mode=trading_mode,
                    confirm_live=confirm_live,
                )
                results.append({"order_id": str(oid), "ok": True})
                stats["ok"] += 1
                if isinstance(r, dict) and r.get("order"):
                    refreshed.append(r["order"])
            except Exception as e:
                results.append({"order_id": str(oid), "ok": False, "error": str(e)})
                stats["failed"] += 1

        return {"orders": refreshed or orders, "results": results, "stats": stats}

    async def cancel_plan(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        trading_mode: str = "paper",
        confirm_live: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        if trading_mode not in {"paper", "live"}:
            raise ValueError("invalid trading_mode")

        if trading_mode == "live":
            self._require_live_enabled(confirm_live=confirm_live)

        orders = await OrderService.get_orders(user_id=user_id, plan_id=plan_id, trading_mode=trading_mode, limit=limit)
        results: list[dict[str, Any]] = []
        stats = {"total": 0, "ok": 0, "skipped": 0, "failed": 0}

        if trading_mode == "paper":
            for o in orders:
                oid = o.get("id")
                if not oid:
                    continue
                stats["total"] += 1
                if (o.get("status") in {"filled", "cancelled", "rejected"}):
                    results.append({"order_id": str(oid), "ok": True, "skipped": True})
                    stats["ok"] += 1
                    stats["skipped"] += 1
                    continue
                try:
                    await self._update_order_status(
                        user_id=user_id,
                        order_id=oid,
                        status="cancelled",
                        trading_mode=trading_mode,
                    )
                    results.append({"order_id": str(oid), "ok": True})
                    stats["ok"] += 1
                except Exception as e:
                    results.append({"order_id": str(oid), "ok": False, "error": str(e)})
                    stats["failed"] += 1
            return {"orders": orders, "results": results, "stats": stats}

        terminal_statuses = {"filled", "cancelled", "rejected"}

        refreshed: list[dict[str, Any]] = []
        failed: list[str] = []
        for o in orders:
            oid = o.get("id")
            if not oid:
                continue
            stats["total"] += 1
            if (o.get("status") in terminal_statuses):
                results.append({"order_id": str(oid), "ok": True, "skipped": True})
                refreshed.append(o)
                stats["ok"] += 1
                stats["skipped"] += 1
                continue
            try:
                r = await self.cancel_order(
                    user_id=user_id,
                    order_id=oid,
                    confirm_live=confirm_live,
                    trading_mode=trading_mode,
                )
                results.append({"order_id": str(oid), "ok": True})
                stats["ok"] += 1
                if isinstance(r, dict) and r.get("order"):
                    refreshed.append(r["order"])
            except Exception as e:
                failed.append(str(e))
                results.append({"order_id": str(oid), "ok": False, "error": str(e)})
                stats["failed"] += 1

        await self._update_execution_plan(
            plan_id=plan_id,
            trading_mode=trading_mode,
            status="cancelled",
            error_message=("; ".join(failed[:3]) if failed else None),
        )
        return {"orders": refreshed or orders, "results": results, "stats": stats}

    async def reconcile_plan(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        trading_mode: str = "paper",
        confirm_live: bool = False,
        limit: int = 20,
        max_rounds: int = 5,
        sleep_ms: int = 500,
        auto_cancel: bool = False,
        max_age_seconds: Optional[int] = None,
    ) -> dict[str, Any]:
        if max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")
        if sleep_ms < 0:
            raise ValueError("sleep_ms must be >= 0")

        if max_age_seconds is not None and max_age_seconds < 1:
            raise ValueError("max_age_seconds must be >= 1")

        plan_started_at = await self._get_execution_plan_started_at(
            user_id=user_id,
            plan_id=plan_id,
            trading_mode=trading_mode,
        )

        last = await self.refresh_plan(
            user_id=user_id,
            plan_id=plan_id,
            trading_mode=trading_mode,
            confirm_live=confirm_live,
            limit=limit,
        )
        orders = (last or {}).get("orders") if isinstance(last, dict) else []
        def _is_terminal(status: Optional[str]) -> bool:
            if not status:
                return False
            return status in {"filled", "cancelled", "rejected"}

        def _all_terminal(os_: list[dict[str, Any]]) -> bool:
            if not os_:
                return True
            return all(_is_terminal((o or {}).get("status")) for o in os_)

        def _has_rejected(os_: list[dict[str, Any]]) -> bool:
            return any(((o or {}).get("status") == "rejected") for o in (os_ or []))

        def _round_summary(payload: Any) -> dict[str, Any]:
            if not isinstance(payload, dict):
                return {"orders": 0, "status_counts": {}, "terminal": True, "rejected": False}
            os_ = payload.get("orders")
            if not isinstance(os_, list):
                os_ = []
            counts: dict[str, int] = {}
            for o in os_:
                if not isinstance(o, dict):
                    continue
                st = o.get("status") or "unknown"
                counts[str(st)] = counts.get(str(st), 0) + 1
            return {
                "orders": len(os_),
                "status_counts": counts,
                "terminal": _all_terminal(os_),
                "rejected": _has_rejected(os_),
            }

        rounds_summary: list[dict[str, Any]] = [_round_summary(last)]
        timeout = False
        max_rounds_exhausted = False
        for _ in range(max(0, max_rounds - 1)):
            if _all_terminal(orders):
                break

            if max_age_seconds is not None and plan_started_at is not None:
                now = datetime.now(timezone.utc)
                started = plan_started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                age_s = (now - started).total_seconds()
                if age_s >= float(max_age_seconds):
                    last = await self.refresh_plan(
                        user_id=user_id,
                        plan_id=plan_id,
                        trading_mode=trading_mode,
                        confirm_live=confirm_live,
                        limit=limit,
                    )
                    rounds_summary.append(_round_summary(last))
                    orders = (last or {}).get("orders") if isinstance(last, dict) else []
                    timeout = True
                    break

            if sleep_ms:
                await asyncio.sleep(sleep_ms / 1000.0)
            last = await self.refresh_plan(
                user_id=user_id,
                plan_id=plan_id,
                trading_mode=trading_mode,
                confirm_live=confirm_live,
                limit=limit,
            )
            rounds_summary.append(_round_summary(last))
            orders = (last or {}).get("orders") if isinstance(last, dict) else []

        if (not timeout) and (not _all_terminal(orders)) and (len(rounds_summary) >= max_rounds):
            try:
                last = await self.refresh_plan(
                    user_id=user_id,
                    plan_id=plan_id,
                    trading_mode=trading_mode,
                    confirm_live=confirm_live,
                    limit=limit,
                )
                rounds_summary.append(_round_summary(last))
                orders = (last or {}).get("orders") if isinstance(last, dict) else []
            except Exception:
                pass
            max_rounds_exhausted = True

        terminal = _all_terminal(orders)
        rejected = _has_rejected(orders)

        age_seconds: Optional[int] = None
        if plan_started_at is not None:
            now = datetime.now(timezone.utc)
            started = plan_started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            try:
                age_seconds = int((now - started).total_seconds())
            except Exception:
                age_seconds = None

        summary = {
            "plan_id": str(plan_id),
            "terminal": terminal,
            "rejected": rejected,
            "rounds": len(rounds_summary),
            "auto_cancel": bool(auto_cancel),
            "max_rounds": max_rounds,
            "max_rounds_exhausted": bool(max_rounds_exhausted),
            "max_age_seconds": max_age_seconds,
            "age_seconds": age_seconds,
            "timeout": bool(timeout),
            "last_status_counts": {},
            "next_action": "reconcile_again",
        }

        summary["reconcile_stats"] = {
            "rounds": len(rounds_summary),
            "timeout": bool(timeout),
            "max_rounds": max_rounds,
            "max_rounds_exhausted": bool(max_rounds_exhausted),
            "auto_cancel_attempted": False,
            "auto_cancel_succeeded": False,
            "cancel_error": None,
        }

        def _update_orders_summary() -> None:
            counts = summary.get("last_status_counts")
            if not isinstance(counts, dict):
                counts = {}
            total_orders = 0
            for v in counts.values():
                try:
                    total_orders += int(v)
                except Exception:
                    continue
            terminal_count = int(counts.get("filled") or 0) + int(counts.get("cancelled") or 0) + int(counts.get("rejected") or 0)
            non_terminal_count = max(0, total_orders - terminal_count)
            summary["orders_summary"] = {
                "total": total_orders,
                "terminal": terminal_count,
                "non_terminal": non_terminal_count,
                "status_counts": counts,
            }

        if rounds_summary and isinstance(rounds_summary[-1], dict):
            last_counts = rounds_summary[-1].get("status_counts")
            if isinstance(last_counts, dict):
                summary["last_status_counts"] = last_counts

        try:
            if isinstance(summary.get("reconcile_stats"), dict):
                summary["reconcile_stats"]["rounds"] = len(rounds_summary)
        except Exception:
            pass

        try:
            preview = self.preview_next_action(
                terminal=terminal,
                auto_cancel=auto_cancel,
                timeout=timeout,
                max_rounds_exhausted=max_rounds_exhausted,
                last_status_counts=summary.get("last_status_counts"),
            )
            if isinstance(preview, dict):
                if isinstance(preview.get("last_status_counts"), dict):
                    summary["last_status_counts"] = preview["last_status_counts"]
                if isinstance(preview.get("next_action"), str):
                    summary["next_action"] = preview["next_action"]
        except Exception:
            summary["next_action"] = "manual_investigate"

        if summary.get("next_action") == "consider_auto_cancel":
            summary["suggested_request"] = self._build_reconcile_suggested_request(
                plan_id=plan_id,
                trading_mode=trading_mode,
                confirm_live=confirm_live,
                limit=limit,
                max_rounds=max_rounds,
                sleep_ms=sleep_ms,
                auto_cancel=True,
                max_age_seconds=max_age_seconds,
                apply_env_defaults=True,
                override_if_default_value=False,
            )

        try:
            _update_orders_summary()
        except Exception:
            pass

        if auto_cancel and (not terminal):
            try:
                try:
                    if isinstance(summary.get("reconcile_stats"), dict):
                        summary["reconcile_stats"]["auto_cancel_attempted"] = True
                except Exception:
                    pass
                cancelled = await self.cancel_plan(
                    user_id=user_id,
                    plan_id=plan_id,
                    trading_mode=trading_mode,
                    confirm_live=confirm_live,
                    limit=limit,
                )
                summary["status"] = "cancelled"
                summary["next_action"] = "none"

                try:
                    if isinstance(summary.get("reconcile_stats"), dict):
                        summary["reconcile_stats"]["auto_cancel_attempted"] = True
                        summary["reconcile_stats"]["auto_cancel_succeeded"] = True
                        summary["reconcile_stats"]["cancel_error"] = None
                except Exception:
                    pass

                try:
                    last = await self.refresh_plan(
                        user_id=user_id,
                        plan_id=plan_id,
                        trading_mode=trading_mode,
                        confirm_live=confirm_live,
                        limit=limit,
                    )
                    rounds_summary.append(_round_summary(last))
                    orders = (last or {}).get("orders") if isinstance(last, dict) else []
                    terminal = _all_terminal(orders)
                    rejected = _has_rejected(orders)
                    summary["terminal"] = terminal
                    summary["rejected"] = rejected
                    summary["rounds"] = len(rounds_summary)
                    try:
                        if isinstance(summary.get("reconcile_stats"), dict):
                            summary["reconcile_stats"]["rounds"] = len(rounds_summary)
                    except Exception:
                        pass
                    if rounds_summary and isinstance(rounds_summary[-1], dict):
                        last_counts = rounds_summary[-1].get("status_counts")
                        if isinstance(last_counts, dict):
                            summary["last_status_counts"] = last_counts
                    try:
                        _update_orders_summary()
                    except Exception:
                        pass
                except Exception:
                    pass

            except Exception as e:
                cancelled = {"error": str(e)}
                summary["status"] = "failed"
                summary["reason"] = f"auto_cancel_failed: {e}"
                summary["next_action"] = "manual_investigate"
                try:
                    if isinstance(summary.get("reconcile_stats"), dict):
                        summary["reconcile_stats"]["auto_cancel_attempted"] = True
                        summary["reconcile_stats"]["auto_cancel_succeeded"] = False
                        summary["reconcile_stats"]["cancel_error"] = str(e)
                except Exception:
                    pass
                try:
                    await self._update_execution_plan(
                        plan_id=plan_id,
                        trading_mode=trading_mode,
                        status="failed",
                        error_message=summary["reason"],
                    )
                except Exception:
                    pass

            try:
                _update_orders_summary()
            except Exception:
                pass

            try:
                legs_payload = await self._get_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode)
                if not isinstance(legs_payload, list):
                    legs_payload = []
                legs_payload.append({"kind": "reconcile_summary", "summary": summary})
                await self._set_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode, legs=legs_payload)
            except Exception:
                pass

            return {"reconciled": last, "rounds": rounds_summary, "auto_cancel": True, "cancel_result": cancelled, "summary": summary}

        status_to_set = None
        if terminal:
            status_to_set = "failed" if rejected else "completed"
        else:
            status_to_set = "failed"
        summary["status"] = status_to_set

        reason: Optional[str] = None
        if status_to_set == "failed":
            if rejected:
                reason = "rejected"
            elif timeout:
                reason = f"timeout (age_seconds={age_seconds}, max_age_seconds={max_age_seconds})"
            elif not terminal and max_rounds_exhausted:
                reason = f"max_rounds_exhausted (max_rounds={max_rounds}, rounds={len(rounds_summary)})"
            elif not terminal:
                reason = f"not_terminal (rounds={len(rounds_summary)})"
        if reason is not None:
            summary["reason"] = reason

        try:
            await self._update_execution_plan(
                plan_id=plan_id,
                trading_mode=trading_mode,
                status=status_to_set,
                error_message=(reason if status_to_set == "failed" else None),
            )
        except Exception:
            pass

        if status_to_set == "completed":
            try:
                plan = await self.get_execution_plan(user_id=user_id, plan_id=plan_id, trading_mode=trading_mode)
                kind = (plan or {}).get("kind") if isinstance(plan, dict) else None
                await self._record_plan_pnl(
                    user_id=user_id,
                    plan_id=plan_id,
                    trading_mode=trading_mode,
                    kind=kind or "unknown",
                )
            except Exception:
                pass

        try:
            legs_payload = await self._get_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode)
            if not isinstance(legs_payload, list):
                legs_payload = []
            legs_payload.append({"kind": "reconcile_summary", "summary": summary})
            await self._set_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode, legs=legs_payload)
        except Exception:
            pass

        return {"reconciled": last, "rounds": rounds_summary, "auto_cancel": False, "summary": summary}

    @staticmethod
    def preview_next_action(
        *,
        terminal: bool,
        auto_cancel: bool,
        timeout: bool,
        max_rounds_exhausted: bool,
        last_status_counts: Optional[dict[str, int]] = None,
    ) -> dict[str, Any]:
        counts: dict[str, int] = {}
        if isinstance(last_status_counts, dict):
            for k, v in last_status_counts.items():
                try:
                    counts[str(k)] = int(v)
                except Exception:
                    continue

        has_non_terminal = bool(counts.get("pending") or counts.get("partially_filled"))
        next_action = "reconcile_again"
        if terminal:
            next_action = "none"
        elif auto_cancel:
            next_action = "wait_cancel"
        elif timeout or max_rounds_exhausted:
            next_action = "consider_auto_cancel" if has_non_terminal else "reconcile_again"

        allowed_next_actions = {"none", "reconcile_again", "consider_auto_cancel", "wait_cancel", "manual_investigate"}
        if next_action not in allowed_next_actions:
            next_action = "manual_investigate"

        return {
            "next_action": next_action,
            "allowed_next_actions": sorted(list(allowed_next_actions)),
            "last_status_counts": counts,
        }

    async def _get_latest_decision(self, user_id: UUID, limit: int = 1) -> dict:
        redis = await get_redis()
        fetch_size = max(50, limit)
        members = await redis.zrange("decisions:latest", 0, max(0, fetch_size - 1), withscores=False)
        if not members:
            raise RuntimeError("no decisions")

        allowed_symbols = await self._get_enabled_symbols(user_id)
        if not allowed_symbols:
            raise RuntimeError("no enabled trading pairs for execution")

        for raw in members:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            try:
                decision = json.loads(raw)
            except Exception:
                continue
            if self._decision_allowed(decision, allowed_symbols):
                return decision

        raise RuntimeError("no decisions for enabled trading pairs")

    async def _get_enabled_symbols(self, user_id: UUID) -> set[str]:
        try:
            config = await get_config_service()
            pairs = await config.get_pairs_for_exchange(self.exchange_id, user_id=user_id, enabled_only=True)
            return {p.symbol for p in (pairs or []) if p.symbol and p.is_active}
        except Exception:
            return set()

    def _decision_allowed(self, decision: dict, allowed_symbols: set[str]) -> bool:
        if not allowed_symbols:
            return False
        exchange = decision.get("exchange") or decision.get("exchange_id") or self.exchange_id
        if exchange != self.exchange_id:
            return False
        raw = decision.get("rawOpportunity") or decision.get("raw_opportunity") or {}
        symbols = raw.get("symbols")
        if isinstance(symbols, list) and symbols:
            for s in symbols:
                if isinstance(s, str) and s not in allowed_symbols:
                    return False
            return True
        symbol = decision.get("symbol") or ""
        if isinstance(symbol, str) and symbol:
            return symbol in allowed_symbols
        return False

    async def _record_plan_pnl(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        trading_mode: str,
        kind: str,
    ) -> None:
        redis = await get_redis()
        dedupe_key = f"pnl:plan:{trading_mode}:{plan_id}"
        if await redis.get(dedupe_key):
            return

        orders, fills = await self._collect_plan_fills(
            user_id=user_id,
            plan_id=plan_id,
            trading_mode=trading_mode,
        )
        if not fills:
            return

        estimate = self._estimate_plan_pnl(orders=orders, fills=fills)
        if not estimate:
            return

        estimate_payload = json.loads(json.dumps(estimate, default=str))

        symbol = estimate.get("symbol") or "MULTI"
        profit = estimate.get("profit")
        profit_rate = estimate.get("profit_rate")
        if profit is None:
            return

        await PnLService.record_pnl(
            user_id=user_id,
            strategy_id=None,
            exchange_id=self.exchange_id,
            symbol=symbol,
            profit=profit,
            profit_rate=profit_rate,
            trading_mode=trading_mode,
            metadata={
                **estimate_payload,
                "plan_id": str(plan_id),
                "kind": kind,
                "trading_mode": trading_mode,
            },
        )

        await redis.set(dedupe_key, "1", ex=3600)

        try:
            legs_payload = await self._get_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode)
            if not isinstance(legs_payload, list):
                legs_payload = []
            legs_payload.append({"kind": "pnl_summary", "summary": estimate_payload})
            await self._set_execution_plan_legs(plan_id=plan_id, trading_mode=trading_mode, legs=legs_payload)
        except Exception:
            pass

    async def _collect_plan_fills(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        trading_mode: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        orders = await OrderService.get_orders(
            user_id=user_id,
            plan_id=plan_id,
            trading_mode=trading_mode,
            limit=1000,
        )
        order_ids = [o.get("id") for o in orders if o.get("id")]
        fills = await OrderService.get_fills(
            order_ids=order_ids,
            trading_mode=trading_mode,
            limit=5000,
        )
        return orders, fills

    def _estimate_plan_pnl(
        self,
        *,
        orders: list[dict[str, Any]],
        fills: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if not fills:
            return None

        order_side = {str(o.get("id")): (o.get("side") or "").lower() for o in orders}
        order_symbol = {str(o.get("id")): o.get("symbol") for o in orders}

        net_notional = Decimal("0")
        total_abs = Decimal("0")
        total_fee = Decimal("0")
        symbols: set[str] = set()
        quotes: set[str] = set()

        for f in fills:
            oid = str(f.get("order_id") or "")
            side = order_side.get(oid)
            price = Decimal(str(f.get("price") or 0))
            qty = Decimal(str(f.get("quantity") or 0))
            notional = price * qty
            fee = Decimal(str(f.get("fee") or 0))
            total_fee += fee

            sym = f.get("symbol") or order_symbol.get(oid)
            if sym:
                symbols.add(str(sym))
                if "/" in str(sym):
                    quotes.add(str(sym).split("/", 1)[1])

            if side == "buy":
                net_notional -= notional
                total_abs += abs(notional)
            elif side == "sell":
                net_notional += notional
                total_abs += abs(notional)

        profit = net_notional - total_fee
        profit_rate = None
        quote_currency = None
        if len(quotes) == 1:
            quote_currency = list(quotes)[0]
        if total_abs > 0:
            try:
                profit_rate = (profit / total_abs).quantize(Decimal("0.00000001"))
            except Exception:
                profit_rate = None

        symbol = symbols.pop() if len(symbols) == 1 else None

        return {
            "symbol": symbol,
            "quote_currency": quote_currency,
            "profit": profit,
            "profit_rate": profit_rate,
            "total_notional": total_abs,
            "total_fee": total_fee,
            "symbols": sorted(list(symbols)) if symbols else ([] if symbol else []),
        }

    async def _execute_cashcarry(self, *, user_id: UUID, decision: dict, trading_mode: str, plan_id: UUID) -> OmsExecutionResult:
        symbol = decision.get("symbol")
        direction = decision.get("direction")
        exposure = Decimal(str(decision.get("estimatedExposure") or "1000"))

        if not symbol or not direction:
            raise ValueError("invalid decision")

        spot_side, perp_side = self._cashcarry_sides(direction)

        spot_bba = await self._repo.get_best_bid_ask(self.exchange_id, symbol, account_type="spot")
        spot_tob = await self._repo.get_orderbook_tob(self.exchange_id, symbol)
        spot_bid = spot_tob.best_bid_price if spot_tob.best_bid_price is not None else (spot_bba.bid if spot_bba.bid is not None else spot_bba.last)
        spot_ask = spot_tob.best_ask_price if spot_tob.best_ask_price is not None else (spot_bba.ask if spot_bba.ask is not None else spot_bba.last)

        perp_bba = await self._repo.get_best_bid_ask(self.exchange_id, symbol, account_type="perp")
        perp_bid = perp_bba.bid if perp_bba.bid is not None else perp_bba.last
        perp_ask = perp_bba.ask if perp_bba.ask is not None else perp_bba.last

        if spot_bid is None or spot_ask is None or perp_bid is None or perp_ask is None:
            raw_op = decision.get("rawOpportunity") or decision.get("raw_opportunity") or {}

            def _coerce(v: Any) -> Optional[float]:
                if v is None:
                    return None
                if isinstance(v, str) and v.strip() == "":
                    return None
                try:
                    return float(v)
                except Exception:
                    return None

            if spot_bid is None:
                spot_bid = _coerce(raw_op.get("spotBid"))
                if spot_bid is None:
                    spot_bid = _coerce(raw_op.get("spotPrice"))

            if spot_ask is None:
                spot_ask = _coerce(raw_op.get("spotAsk"))
                if spot_ask is None:
                    spot_ask = _coerce(raw_op.get("spotPrice"))
                if spot_ask is None:
                    spot_ask = spot_bid

            if perp_bid is None:
                perp_bid = _coerce(raw_op.get("perpBid"))
                if perp_bid is None:
                    perp_bid = _coerce(raw_op.get("perpPrice"))

            if perp_ask is None:
                perp_ask = _coerce(raw_op.get("perpAsk"))
                if perp_ask is None:
                    perp_ask = _coerce(raw_op.get("perpPrice"))
                if perp_ask is None:
                    perp_ask = perp_bid

        if spot_bid is None or spot_ask is None or perp_bid is None or perp_ask is None:
            raise RuntimeError("missing market data")

        spot_price = Decimal(str(spot_ask if spot_side == "buy" else spot_bid))
        perp_price = Decimal(str(perp_ask if perp_side == "buy" else perp_bid))

        spot_qty = (exposure / spot_price).quantize(Decimal("0.00000001"))
        perp_qty = spot_qty

        orders: list[dict[str, Any]] = []
        spot_leg_id = "spot"
        spot_client_order_id = f"{plan_id}-spot"
        spot_order_id = await OrderService.create_order(
            user_id=user_id,
            strategy_id=None,
            exchange_id=self.exchange_id,
            symbol=symbol,
            side=spot_side,
            order_type="market",
            quantity=spot_qty,
            price=None,
            trading_mode=trading_mode,
            metadata={"ref_price": str(spot_price), "decision": decision},
            client_order_id=spot_client_order_id,
            account_type="spot",
            plan_id=plan_id,
            leg_id=spot_leg_id,
        )

        if trading_mode == "paper":
            spot_fee = (exposure * self.spot_fee_rate).quantize(Decimal("0.00000001"))
            await self._update_order_status(
                user_id=user_id,
                order_id=spot_order_id,
                status="filled",
                filled_quantity=spot_qty,
                average_price=spot_price,
                fee=spot_fee,
                trading_mode=trading_mode,
            )
            await OrderService.create_fill(
                user_id=user_id,
                order_id=spot_order_id,
                exchange_id=self.exchange_id,
                account_type="spot",
                symbol=symbol,
                price=spot_price,
                quantity=spot_qty,
                fee=spot_fee,
                fee_currency="USDT",
                trading_mode=trading_mode,
            )
        else:
            spot_exec = await self._live_market_order(
                account_type="spot",
                symbol=symbol,
                side=spot_side,
                quantity=spot_qty,
                client_order_id=spot_client_order_id,
            )
            await self._update_order_status(
                user_id=user_id,
                order_id=spot_order_id,
                status=spot_exec["status"],
                filled_quantity=spot_exec["filled_quantity"],
                average_price=spot_exec["average_price"],
                fee=spot_exec["fee"],
                fee_currency=spot_exec.get("fee_currency"),
                external_order_id=spot_exec["external_order_id"],
                trading_mode=trading_mode,
            )
            fills = spot_exec.get("fills") or []
            if not fills and spot_exec.get("filled_quantity") and spot_exec.get("average_price"):
                fills = [
                    {
                        "price": spot_exec["average_price"],
                        "quantity": spot_exec["filled_quantity"],
                        "fee": spot_exec.get("fee"),
                        "fee_currency": spot_exec.get("fee_currency"),
                        "external_trade_id": spot_exec.get("external_trade_id"),
                        "raw": spot_exec.get("raw"),
                    }
                ]
            for f in fills:
                ext_trade_id = f.get("external_trade_id")
                if ext_trade_id and await OrderService.fill_exists(ext_trade_id, trading_mode=trading_mode):
                    continue
                await OrderService.create_fill(
                    user_id=user_id,
                    order_id=spot_order_id,
                    exchange_id=self.exchange_id,
                    account_type="spot",
                    symbol=symbol,
                    price=f["price"],
                    quantity=f["quantity"],
                    fee=f.get("fee"),
                    fee_currency=f.get("fee_currency"),
                    external_trade_id=ext_trade_id,
                    external_order_id=spot_exec["external_order_id"],
                    raw=f.get("raw") or spot_exec.get("raw"),
                    trading_mode=trading_mode,
                )

        orders.append({"order_id": str(spot_order_id), "account_type": "spot", "symbol": symbol, "side": spot_side, "quantity": str(spot_qty), "average_price": str(spot_price)})

        perp_leg_id = "perp"
        perp_client_order_id = f"{plan_id}-perp"
        perp_order_id = await OrderService.create_order(
            user_id=user_id,
            strategy_id=None,
            exchange_id=self.exchange_id,
            symbol=symbol,
            side=perp_side,
            order_type="market",
            quantity=perp_qty,
            price=None,
            trading_mode=trading_mode,
            metadata={"ref_price": str(perp_price), "decision": decision},
            client_order_id=perp_client_order_id,
            account_type="perp",
            plan_id=plan_id,
            leg_id=perp_leg_id,
        )

        if trading_mode == "paper":
            perp_fee = (exposure * self.perp_fee_rate).quantize(Decimal("0.00000001"))
            await self._update_order_status(
                user_id=user_id,
                order_id=perp_order_id,
                status="filled",
                filled_quantity=perp_qty,
                average_price=perp_price,
                fee=perp_fee,
                trading_mode=trading_mode,
            )
            await OrderService.create_fill(
                user_id=user_id,
                order_id=perp_order_id,
                exchange_id=self.exchange_id,
                account_type="perp",
                symbol=symbol,
                price=perp_price,
                quantity=perp_qty,
                fee=perp_fee,
                fee_currency="USDT",
                trading_mode=trading_mode,
            )
        else:
            perp_exec = await self._live_market_order(
                account_type="perp",
                symbol=symbol,
                side=perp_side,
                quantity=perp_qty,
                client_order_id=perp_client_order_id,
            )
            await self._update_order_status(
                user_id=user_id,
                order_id=perp_order_id,
                status=perp_exec["status"],
                filled_quantity=perp_exec["filled_quantity"],
                average_price=perp_exec["average_price"],
                fee=perp_exec["fee"],
                fee_currency=perp_exec.get("fee_currency"),
                external_order_id=perp_exec["external_order_id"],
                trading_mode=trading_mode,
            )
            fills = perp_exec.get("fills") or []
            if not fills and perp_exec.get("filled_quantity") and perp_exec.get("average_price"):
                fills = [
                    {
                        "price": perp_exec["average_price"],
                        "quantity": perp_exec["filled_quantity"],
                        "fee": perp_exec.get("fee"),
                        "fee_currency": perp_exec.get("fee_currency"),
                        "external_trade_id": perp_exec.get("external_trade_id"),
                        "raw": perp_exec.get("raw"),
                    }
                ]
            for f in fills:
                ext_trade_id = f.get("external_trade_id")
                if ext_trade_id and await OrderService.fill_exists(ext_trade_id, trading_mode=trading_mode):
                    continue
                await OrderService.create_fill(
                    user_id=user_id,
                    order_id=perp_order_id,
                    exchange_id=self.exchange_id,
                    account_type="perp",
                    symbol=symbol,
                    price=f["price"],
                    quantity=f["quantity"],
                    fee=f.get("fee"),
                    fee_currency=f.get("fee_currency"),
                    external_trade_id=ext_trade_id,
                    external_order_id=perp_exec["external_order_id"],
                    raw=f.get("raw") or perp_exec.get("raw"),
                    trading_mode=trading_mode,
                )

        orders.append({"order_id": str(perp_order_id), "account_type": "perp", "symbol": symbol, "side": perp_side, "quantity": str(perp_qty), "average_price": str(perp_price)})

        return OmsExecutionResult(decision=decision, orders=orders)

    async def _execute_triangular(self, *, user_id: UUID, decision: dict, trading_mode: str, plan_id: UUID) -> OmsExecutionResult:
        raw = decision.get("rawOpportunity") or {}
        symbols = raw.get("symbols") or []
        path = raw.get("path") or ""

        if not isinstance(symbols, list) or len(symbols) != 3:
            raise ValueError("invalid triangular opportunity")

        if not isinstance(path, str) or "->" not in path:
            raise ValueError("invalid triangular path")

        currencies = [p.strip() for p in path.split("->")]
        if len(currencies) != 4:
            raise ValueError("invalid triangular path")

        start_amount = Decimal(str(decision.get("estimatedExposure") or "1000"))
        current_amount = start_amount

        orders: list[dict[str, Any]] = []
        for i in range(3):
            u = currencies[i]
            v = currencies[i + 1]
            symbol = symbols[i]
            base, quote = symbol.split("/", 1)

            if quote == u and base == v:
                side = "buy"
                tob = await self._repo.get_orderbook_tob(self.exchange_id, symbol)
                bba = await self._repo.get_best_bid_ask(self.exchange_id, symbol, account_type="spot")
                ask = tob.best_ask_price if tob.best_ask_price is not None else (bba.ask if bba.ask is not None else bba.last)
                if ask is None or float(ask) <= 0:
                    raise RuntimeError("missing spot ask")
                price = Decimal(str(ask))
                qty = (current_amount / price).quantize(Decimal("0.00000001"))
                fee = (current_amount * self.spot_fee_rate).quantize(Decimal("0.00000001"))
                current_amount = (current_amount - fee) / price
            elif base == u and quote == v:
                side = "sell"
                tob = await self._repo.get_orderbook_tob(self.exchange_id, symbol)
                bba = await self._repo.get_best_bid_ask(self.exchange_id, symbol, account_type="spot")
                bid = tob.best_bid_price if tob.best_bid_price is not None else (bba.bid if bba.bid is not None else bba.last)
                if bid is None or float(bid) <= 0:
                    raise RuntimeError("missing spot bid")
                price = Decimal(str(bid))
                qty = current_amount.quantize(Decimal("0.00000001"))
                fee = (current_amount * price * self.spot_fee_rate).quantize(Decimal("0.00000001"))
                current_amount = (current_amount * price) - fee
            else:
                raise ValueError("triangular symbol/path mismatch")

            leg_id = f"leg{i + 1}"
            client_order_id = f"{plan_id}-{leg_id}"
            order_id = await OrderService.create_order(
                user_id=user_id,
                strategy_id=None,
                exchange_id=self.exchange_id,
                symbol=symbol,
                side=side,
                order_type="market",
                quantity=qty,
                price=None,
                trading_mode=trading_mode,
                metadata={"ref_price": str(price), "leg": i + 1, "decision": decision},
                client_order_id=client_order_id,
                account_type="spot",
                plan_id=plan_id,
                leg_id=leg_id,
            )
            if trading_mode == "paper":
                await self._update_order_status(
                    user_id=user_id,
                    order_id=order_id,
                    status="filled",
                    filled_quantity=qty,
                    average_price=price,
                    fee=fee,
                    trading_mode=trading_mode,
                )
                await OrderService.create_fill(
                    user_id=user_id,
                    order_id=order_id,
                    exchange_id=self.exchange_id,
                    account_type="spot",
                    symbol=symbol,
                    price=price,
                    quantity=qty,
                    fee=fee,
                    fee_currency=quote,
                    trading_mode=trading_mode,
                )
            else:
                live_exec = await self._live_market_order(
                    account_type="spot",
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    client_order_id=client_order_id,
                )
                await self._update_order_status(
                    user_id=user_id,
                    order_id=order_id,
                    status=live_exec["status"],
                    filled_quantity=live_exec["filled_quantity"],
                    average_price=live_exec["average_price"],
                    fee=live_exec["fee"],
                    fee_currency=live_exec.get("fee_currency"),
                    external_order_id=live_exec["external_order_id"],
                    trading_mode=trading_mode,
                )
                fills = live_exec.get("fills") or []
                if not fills and live_exec.get("filled_quantity") and live_exec.get("average_price"):
                    fills = [
                        {
                            "price": live_exec["average_price"],
                            "quantity": live_exec["filled_quantity"],
                            "fee": live_exec.get("fee"),
                            "fee_currency": live_exec.get("fee_currency"),
                            "external_trade_id": live_exec.get("external_trade_id"),
                            "raw": live_exec.get("raw"),
                        }
                    ]
                for f in fills:
                    ext_trade_id = f.get("external_trade_id")
                    if ext_trade_id and await OrderService.fill_exists(ext_trade_id, trading_mode=trading_mode):
                        continue
                    await OrderService.create_fill(
                        user_id=user_id,
                        order_id=order_id,
                        exchange_id=self.exchange_id,
                        account_type="spot",
                        symbol=symbol,
                        price=f["price"],
                        quantity=f["quantity"],
                        fee=f.get("fee"),
                        fee_currency=f.get("fee_currency"),
                        external_trade_id=ext_trade_id,
                        external_order_id=live_exec["external_order_id"],
                        raw=f.get("raw") or live_exec.get("raw"),
                        trading_mode=trading_mode,
                    )
            orders.append({"order_id": str(order_id), "account_type": "spot", "symbol": symbol, "side": side, "quantity": str(qty), "average_price": str(price)})

        return OmsExecutionResult(decision=decision, orders=orders)

    @staticmethod
    def _cashcarry_sides(direction: str) -> tuple[str, str]:
        if direction == "long_spot_short_perp":
            return "buy", "sell"
        if direction == "short_spot_long_perp":
            return "sell", "buy"
        raise ValueError("invalid cashcarry direction")

    async def _create_execution_plan(self, *, user_id: UUID, trading_mode: str, kind: str) -> UUID:
        table_name = 'paper_execution_plans' if trading_mode == 'paper' else 'live_execution_plans'
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            plan_id = await conn.fetchval(
                f"""
                INSERT INTO {table_name} (user_id, exchange_id, kind, status, legs, started_at)
                VALUES ($1, $2, $3, 'running', '[]'::jsonb, NOW())
                RETURNING id
                """,
                user_id,
                self.exchange_id,
                kind,
            )
            return plan_id

    async def _update_execution_plan(self, *, plan_id: UUID, trading_mode: str, status: str, error_message: Optional[str] = None) -> None:
        table_name = 'paper_execution_plans' if trading_mode == 'paper' else 'live_execution_plans'
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {table_name}
                SET status = $2::varchar,
                    finished_at = CASE WHEN $2::varchar IN ('completed','failed','cancelled') THEN NOW() ELSE finished_at END,
                    error_message = COALESCE($3, error_message)
                WHERE id = $1
                """,
                plan_id,
                status,
                error_message,
            )

    async def _set_execution_plan_legs(self, *, plan_id: UUID, trading_mode: str, legs: list[dict[str, Any]]) -> None:
        table_name = 'paper_execution_plans' if trading_mode == 'paper' else 'live_execution_plans'
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {table_name}
                SET legs = $2::jsonb
                WHERE id = $1
                """,
                plan_id,
                json.dumps(legs, ensure_ascii=False, default=str),
            )

    async def _get_execution_plan_legs(self, *, plan_id: UUID, trading_mode: str) -> list[dict[str, Any]]:
        table_name = 'paper_execution_plans' if trading_mode == 'paper' else 'live_execution_plans'
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT legs
                FROM {table_name}
                WHERE id = $1
                """,
                plan_id,
            )
        if not row:
            return []
        legs = row.get('legs')
        if isinstance(legs, str):
            try:
                legs = json.loads(legs)
            except Exception:
                return []
        if not isinstance(legs, list):
            return []
        return legs

    async def _get_execution_plan_started_at(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        trading_mode: str,
    ) -> Optional[datetime]:
        table_name = 'paper_execution_plans' if trading_mode == 'paper' else 'live_execution_plans'
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT started_at, created_at
                FROM {table_name}
                WHERE id = $1 AND user_id = $2
                """,
                plan_id,
                user_id,
            )
        if not row:
            return None
        return row.get('started_at') or row.get('created_at')

    async def _live_market_order(
        self,
        *,
        account_type: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        client_order_id: Optional[str] = None,
    ) -> dict:
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_SECRET_KEY') or os.getenv('BINANCE_API_SECRET')
        if not api_key or not api_secret:
            raise RuntimeError('missing BINANCE_API_KEY/BINANCE_SECRET_KEY')

        testnet = os.getenv('BINANCE_TESTNET', '0').strip() in {'1','true','True'}
        default_type = 'spot' if account_type == 'spot' else 'future'
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': default_type},
        })
        if testnet:
            exchange.set_sandbox_mode(True)

        try:
            await exchange.load_markets()
            qty_f = float(quantity)

            try_symbols = [symbol]
            if account_type == 'perp' and ':' not in symbol and symbol.endswith('/USDT'):
                try_symbols.insert(0, f"{symbol}:USDT")

            last_err: Optional[Exception] = None
            order = None
            used_symbol = None
            for s in try_symbols:
                try:
                    used_symbol = s
                    params = {}
                    if client_order_id:
                        safe_id = self._safe_client_order_id(client_order_id)
                        params = {'newClientOrderId': safe_id, 'clientOrderId': safe_id}
                    order = await exchange.create_market_order(s, side, qty_f, params)
                    break
                except Exception as e:
                    last_err = e
                    continue
            if order is None:
                raise RuntimeError(f'create_market_order failed: {last_err}')
            exec_result = self._extract_exec_from_ccxt_order(order, quantity_fallback=qty_f)
            exec_result["raw"] = {'account_type': account_type, 'used_symbol': used_symbol, 'order': order}
            return exec_result
        finally:
            try:
                await exchange.close()
            except Exception:
                pass

    def _require_live_enabled(self, *, confirm_live: bool) -> None:
        if not confirm_live:
            raise PermissionError("live mode requires confirm_live=true")
        if os.getenv("INARBIT_ENABLE_LIVE_OMS", "0").strip() not in {"1", "true", "True"}:
            raise PermissionError("live mode requires INARBIT_ENABLE_LIVE_OMS=1")

    def _extract_exec_from_ccxt_order(self, order: dict, *, quantity_fallback: float) -> dict:
        fills: list[dict[str, Any]] = []

        raw_trades = order.get('trades')
        if isinstance(raw_trades, list):
            for t in raw_trades:
                if not isinstance(t, dict):
                    continue
                p = t.get('price')
                q = t.get('amount') or t.get('qty')
                if p is None or q is None:
                    continue
                fee_obj = t.get('fee') or {}
                fee_cost = fee_obj.get('cost')
                fee_currency = fee_obj.get('currency')
                fills.append(
                    {
                        'price': Decimal(str(p)).quantize(Decimal('0.00000001')),
                        'quantity': Decimal(str(q)).quantize(Decimal('0.00000001')),
                        'fee': Decimal(str(fee_cost or '0')).quantize(Decimal('0.00000001')),
                        'fee_currency': fee_currency,
                        'external_trade_id': t.get('id') or t.get('tradeId'),
                        'raw': t,
                    }
                )

        raw_fills = order.get('fills')
        if not fills and isinstance(raw_fills, list):
            for f in raw_fills:
                if not isinstance(f, dict):
                    continue
                p = f.get('price')
                q = f.get('amount') or f.get('qty')
                if p is None or q is None:
                    continue
                fee_obj = f.get('fee') or {}
                fee_cost = fee_obj.get('cost')
                fee_currency = fee_obj.get('currency')
                fills.append(
                    {
                        'price': Decimal(str(p)).quantize(Decimal('0.00000001')),
                        'quantity': Decimal(str(q)).quantize(Decimal('0.00000001')),
                        'fee': Decimal(str(fee_cost or '0')).quantize(Decimal('0.00000001')),
                        'fee_currency': fee_currency,
                        'external_trade_id': f.get('id') or f.get('tradeId'),
                        'raw': f,
                    }
                )

        info = order.get('info')
        if not fills and isinstance(info, dict):
            info_fills = info.get('fills')
            if isinstance(info_fills, list):
                for f in info_fills:
                    if not isinstance(f, dict):
                        continue
                    p = f.get('price')
                    q = f.get('qty') or f.get('amount')
                    if p is None or q is None:
                        continue
                    fee_cost = f.get('commission')
                    fee_currency = f.get('commissionAsset')
                    fills.append(
                        {
                            'price': Decimal(str(p)).quantize(Decimal('0.00000001')),
                            'quantity': Decimal(str(q)).quantize(Decimal('0.00000001')),
                            'fee': Decimal(str(fee_cost or '0')).quantize(Decimal('0.00000001')),
                            'fee_currency': fee_currency,
                            'external_trade_id': f.get('tradeId') or f.get('id'),
                            'raw': f,
                        }
                    )

        # 对于缺失 external_trade_id 的成交，生成一个稳定的 synthetic id 用于去重
        external_order_id = str(order.get('id') or '')
        for i, f in enumerate(fills):
            if f.get('external_trade_id'):
                continue
            ts = None
            raw = f.get('raw')
            if isinstance(raw, dict):
                ts = raw.get('timestamp') or raw.get('time') or raw.get('transactTime')
                ts = ts or raw.get('T')
            seed = {
                'external_order_id': external_order_id,
                'i': i,
                'price': str(f.get('price')),
                'quantity': str(f.get('quantity')),
                'fee': str(f.get('fee')),
                'fee_currency': f.get('fee_currency'),
                'ts': ts,
            }
            digest = hashlib.sha256(json.dumps(seed, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
            f['external_trade_id'] = f"synthetic:{external_order_id}:{digest}"

        filled = None
        avg_d = None
        fee_d = None
        fee_currency = None

        if fills:
            filled_total = sum((x['quantity'] for x in fills), Decimal('0'))
            if filled_total > 0:
                vwap_n = sum((x['price'] * x['quantity'] for x in fills), Decimal('0'))
                avg_d = (vwap_n / filled_total).quantize(Decimal('0.00000001'))
            else:
                avg_d = Decimal('0').quantize(Decimal('0.00000001'))
            filled = filled_total.quantize(Decimal('0.00000001'))
            currencies = {x.get('fee_currency') for x in fills if x.get('fee_currency')}
            if len(currencies) == 1:
                fee_currency = next(iter(currencies))
            fee_d = sum((x.get('fee') or Decimal('0') for x in fills), Decimal('0')).quantize(Decimal('0.00000001'))
        else:
            filled = Decimal(str(order.get('filled') or order.get('amount') or quantity_fallback)).quantize(Decimal('0.00000001'))
            avg = order.get('average') or order.get('price')
            if avg is None:
                avg = order.get('cost')
                if avg is not None and float(filled) > 0:
                    avg = float(avg) / float(filled)
            if avg is None:
                avg_d = Decimal('0').quantize(Decimal('0.00000001'))
            else:
                avg_d = Decimal(str(avg)).quantize(Decimal('0.00000001'))

            fee_obj = order.get('fee') or {}
            fee_cost = fee_obj.get('cost')
            fee_currency = fee_obj.get('currency')
            fee_d = Decimal(str(fee_cost or '0')).quantize(Decimal('0.00000001'))

        status = (order.get('status') or 'closed').lower()
        if status in {'closed', 'filled'}:
            mapped_status = 'filled'
        elif status in {'canceled', 'cancelled'}:
            mapped_status = 'cancelled'
        elif status in {'rejected'}:
            mapped_status = 'rejected'
        else:
            mapped_status = 'partially_filled' if filled > 0 else 'pending'

        return {
            'status': mapped_status,
            'filled_quantity': filled,
            'average_price': avg_d,
            'fee': fee_d,
            'fee_currency': fee_currency,
            'external_order_id': str(order.get('id') or ''),
            'external_trade_id': fills[0].get('external_trade_id') if fills else None,
            'fills': fills,
            'raw': {'order': order},
        }

    @staticmethod
    def _safe_client_order_id(value: str) -> str:
        v = (value or '').strip()
        if not v:
            return v
        if len(v) <= 32 and v.replace('-', '').replace('_', '').isalnum():
            return v
        digest = hashlib.sha256(v.encode('utf-8')).hexdigest()[:24]
        return f"inarbit-{digest}"

    async def _fetch_live_order(self, *, account_type: str, symbol: str, external_order_id: str) -> dict:
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_SECRET_KEY') or os.getenv('BINANCE_API_SECRET')
        if not api_key or not api_secret:
            raise RuntimeError('missing BINANCE_API_KEY/BINANCE_SECRET_KEY')

        testnet = os.getenv('BINANCE_TESTNET', '0').strip() in {'1','true','True'}
        default_type = 'spot' if account_type == 'spot' else 'future'
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': default_type},
        })
        if testnet:
            exchange.set_sandbox_mode(True)

        try:
            await exchange.load_markets()
            try_symbols = [symbol]
            if account_type == 'perp' and ':' not in symbol and symbol.endswith('/USDT'):
                try_symbols.insert(0, f"{symbol}:USDT")

            last_err: Optional[Exception] = None
            for s in try_symbols:
                try:
                    o = await exchange.fetch_order(external_order_id, s)
                    return o
                except Exception as e:
                    last_err = e
                    continue
            raise RuntimeError(f'fetch_order failed: {last_err}')
        finally:
            try:
                await exchange.close()
            except Exception:
                pass

    async def _cancel_live_order(self, *, account_type: str, symbol: str, external_order_id: str) -> None:
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_SECRET_KEY') or os.getenv('BINANCE_API_SECRET')
        if not api_key or not api_secret:
            raise RuntimeError('missing BINANCE_API_KEY/BINANCE_SECRET_KEY')

        testnet = os.getenv('BINANCE_TESTNET', '0').strip() in {'1','true','True'}
        default_type = 'spot' if account_type == 'spot' else 'future'
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': default_type},
        })
        if testnet:
            exchange.set_sandbox_mode(True)

        try:
            await exchange.load_markets()
            try_symbols = [symbol]
            if account_type == 'perp' and ':' not in symbol and symbol.endswith('/USDT'):
                try_symbols.insert(0, f"{symbol}:USDT")

            last_err: Optional[Exception] = None
            for s in try_symbols:
                try:
                    await exchange.cancel_order(external_order_id, s)
                    return
                except Exception as e:
                    last_err = e
                    continue
            raise RuntimeError(f'cancel_order failed: {last_err}')
        finally:
            try:
                await exchange.close()
            except Exception:
                pass
