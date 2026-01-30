"""
订单服务 - 支持模拟盘/实盘分表
"""
import json
import logging
import asyncpg
from typing import List, Dict, Optional, Tuple
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from ..db import get_pg_pool

logger = logging.getLogger(__name__)


class OrderService:
    """订单管理服务"""
    
    @staticmethod
    async def create_order(
        user_id: UUID,
        strategy_id: Optional[UUID],
        exchange_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        trading_mode: str = 'paper',
        metadata: Optional[Dict] = None,
        client_order_id: Optional[str] = None,
        account_type: str = 'spot',
        plan_id: Optional[UUID] = None,
        leg_id: Optional[str] = None,
        external_order_id: Optional[str] = None,
    ) -> UUID:
        """
        创建订单
        
        Args:
            trading_mode: 'paper' (模拟盘) 或 'live' (实盘)
        
        Returns:
            订单ID
        """
        # 根据trading_mode选择表
        table_name = 'paper_orders' if trading_mode == 'paper' else 'live_orders'
        
        pool = await get_pg_pool()

        if client_order_id:
            existing = await OrderService.get_order_id_by_client_order_id(
                user_id=user_id,
                client_order_id=client_order_id,
                trading_mode=trading_mode,
            )
            if existing:
                return existing

        metadata_payload = dict(metadata or {})
        if client_order_id is not None:
            metadata_payload.setdefault("client_order_id", client_order_id)
        if account_type is not None:
            metadata_payload.setdefault("account_type", account_type)
        if plan_id is not None:
            metadata_payload.setdefault("plan_id", str(plan_id))
        if leg_id is not None:
            metadata_payload.setdefault("leg_id", leg_id)
        if external_order_id is not None:
            metadata_payload.setdefault("external_order_id", external_order_id)

        metadata_json = json.dumps(metadata_payload, ensure_ascii=False)

        try:
            try:
                order_id = await pool.fetchval(
                    f"""
                    INSERT INTO {table_name} (
                        user_id, strategy_id, exchange_id, symbol, side, order_type,
                        quantity, price, status, metadata,
                        client_order_id, account_type, plan_id, leg_id, external_order_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', $9::jsonb, $10, $11, $12, $13, $14)
                    RETURNING id
                    """,
                    user_id,
                    strategy_id,
                    exchange_id,
                    symbol,
                    side,
                    order_type,
                    quantity,
                    price,
                    metadata_json,
                    client_order_id,
                    account_type,
                    plan_id,
                    leg_id,
                    external_order_id,
                )
            except asyncpg.exceptions.UniqueViolationError:
                if client_order_id:
                    existing = await OrderService.get_order_id_by_client_order_id(
                        user_id=user_id,
                        client_order_id=client_order_id,
                        trading_mode=trading_mode,
                    )
                    if existing:
                        return existing
                raise
            except Exception:
                order_id = await pool.fetchval(
                    f"""
                    INSERT INTO {table_name} (
                        user_id, strategy_id, exchange_id, symbol, side, order_type,
                        quantity, price, status, metadata, external_order_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', $9::jsonb, $10)
                    RETURNING id
                    """,
                    user_id,
                    strategy_id,
                    exchange_id,
                    symbol,
                    side,
                    order_type,
                    quantity,
                    price,
                    metadata_json,
                    external_order_id,
                )
            except asyncpg.exceptions.UniqueViolationError:
                if client_order_id:
                    existing = await OrderService.get_order_id_by_client_order_id(
                        user_id=user_id,
                        client_order_id=client_order_id,
                        trading_mode=trading_mode,
                    )
                    if existing:
                        return existing
                raise
            
            logger.info(
                f"{'📝' if trading_mode == 'paper' else '⚠️'} "
                f"订单已创建 ({trading_mode}): {side} {quantity} {symbol} @ {price or 'MARKET'}"
            )
            
            return order_id
            
        except Exception as e:
            logger.error(f"创建订单失败: {e}")
            raise
    
    @staticmethod
    async def update_order_status(
        order_id: UUID,
        status: str,
        filled_quantity: Optional[Decimal] = None,
        average_price: Optional[Decimal] = None,
        fee: Optional[Decimal] = None,
        fee_currency: Optional[str] = None,
        external_order_id: Optional[str] = None,
        trading_mode: str = 'paper'
    ) -> bool:
        """更新订单状态"""
        table_name = 'paper_orders' if trading_mode == 'paper' else 'live_orders'
        
        pool = await get_pg_pool()
        
        try:
            update_fields = ['status = $2']
            params = [order_id, status]
            param_idx = 3
            
            if filled_quantity is not None:
                update_fields.append(f'filled_quantity = ${param_idx}')
                params.append(filled_quantity)
                param_idx += 1
            
            if average_price is not None:
                update_fields.append(f'average_price = ${param_idx}')
                params.append(average_price)
                param_idx += 1
            
            if fee is not None:
                update_fields.append(f'fee = ${param_idx}')
                params.append(fee)
                param_idx += 1

            if fee_currency is not None:
                update_fields.append(f'fee_currency = ${param_idx}')
                params.append(fee_currency)
                param_idx += 1

            if external_order_id is not None:
                update_fields.append(f'external_order_id = ${param_idx}')
                params.append(external_order_id)
                param_idx += 1
            
            if status == 'filled':
                update_fields.append('filled_at = NOW()')
            
            query = f"""
                UPDATE {table_name}
                SET {', '.join(update_fields)}, updated_at = NOW()
                WHERE id = $1
            """
            
            await pool.execute(query, *params)
            
            logger.info(f"订单状态已更新 ({trading_mode}): {order_id} -> {status}")
            return True
            
        except Exception as e:
            logger.error(f"更新订单状态失败: {e}")
            return False

    @staticmethod
    async def get_order_by_id(
        order_id: UUID,
        trading_mode: str = 'paper',
    ) -> Optional[Dict]:
        table_name = 'paper_orders' if trading_mode == 'paper' else 'live_orders'
        pool = await get_pg_pool()
        try:
            row = await pool.fetchrow(
                f"""
                SELECT *
                FROM {table_name}
                WHERE id = $1
                """,
                order_id,
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"查询订单失败: {e}")
            return None

    @staticmethod
    async def get_order_id_by_client_order_id(
        *,
        user_id: UUID,
        client_order_id: str,
        trading_mode: str = 'paper',
    ) -> Optional[UUID]:
        if not client_order_id:
            return None

        table_name = 'paper_orders' if trading_mode == 'paper' else 'live_orders'
        pool = await get_pg_pool()
        try:
            return await pool.fetchval(
                f"""
                SELECT id
                FROM {table_name}
                WHERE user_id = $1 AND client_order_id = $2
                LIMIT 1
                """,
                user_id,
                client_order_id,
            )
        except Exception:
            return None

    @staticmethod
    async def fill_exists(
        external_trade_id: str,
        trading_mode: str = 'paper',
    ) -> bool:
        if not external_trade_id:
            return False

        table_name = 'paper_fills' if trading_mode == 'paper' else 'live_fills'
        pool = await get_pg_pool()
        try:
            row = await pool.fetchrow(
                f"""
                SELECT id
                FROM {table_name}
                WHERE external_trade_id = $1
                LIMIT 1
                """,
                external_trade_id,
            )
            return row is not None
        except Exception as e:
            logger.error(f"查询成交去重失败: {e}")
            return False

    @staticmethod
    async def create_fill(
        user_id: UUID,
        order_id: UUID,
        exchange_id: str,
        account_type: str,
        symbol: str,
        price: Decimal,
        quantity: Decimal,
        fee: Optional[Decimal] = None,
        fee_currency: Optional[str] = None,
        external_trade_id: Optional[str] = None,
        external_order_id: Optional[str] = None,
        raw: Optional[Dict] = None,
        trading_mode: str = 'paper',
    ) -> Optional[UUID]:
        table_name = 'paper_fills' if trading_mode == 'paper' else 'live_fills'
        pool = await get_pg_pool()

        try:
            raw_json = json.dumps(raw or {}, ensure_ascii=False)
            fill_id = await pool.fetchval(
                f"""
                INSERT INTO {table_name} (
                    user_id, order_id, exchange_id, account_type, symbol,
                    price, quantity, fee, fee_currency,
                    external_trade_id, external_order_id, raw
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
                RETURNING id
                """,
                user_id,
                order_id,
                exchange_id,
                account_type,
                symbol,
                price,
                quantity,
                fee or Decimal('0'),
                fee_currency,
                external_trade_id,
                external_order_id,
                raw_json,
            )
            if fill_id:
                try:
                    await OrderService._apply_fill_side_effects(
                        user_id=user_id,
                        order_id=order_id,
                        exchange_id=exchange_id,
                        account_type=account_type or 'spot',
                        symbol=symbol,
                        price=price,
                        quantity=quantity,
                        fee=fee,
                        fee_currency=fee_currency,
                        trading_mode=trading_mode,
                    )
                except Exception as e:
                    logger.warning(f"更新持仓/账本失败: {e}")
            return fill_id
        except Exception as e:
            logger.error(f"创建成交记录失败: {e}")
            return None

    @staticmethod
    async def _apply_fill_side_effects(
        *,
        user_id: UUID,
        order_id: UUID,
        exchange_id: str,
        account_type: str,
        symbol: str,
        price: Decimal,
        quantity: Decimal,
        fee: Optional[Decimal],
        fee_currency: Optional[str],
        trading_mode: str,
    ) -> None:
        order = await OrderService.get_order_by_id(order_id=order_id, trading_mode=trading_mode)
        if not order:
            return

        side = str(order.get("side") or "").lower()
        if side not in {"buy", "sell"}:
            return

        account_type = (account_type or order.get("account_type") or "spot").lower()
        fee_amount = fee or Decimal('0')

        if account_type == "spot":
            base, quote = OrderService._split_symbol(symbol)
            if not base or not quote:
                return

            qty = quantity
            px = price
            base_delta = qty if side == "buy" else -qty
            quote_delta = (px * qty) * (Decimal('-1') if side == "buy" else Decimal('1'))

            if fee_currency:
                if fee_currency == base:
                    base_delta -= fee_amount
                elif fee_currency == quote:
                    quote_delta -= fee_amount

            await OrderService._upsert_position(
                user_id=user_id,
                exchange_id=exchange_id,
                account_type=account_type,
                instrument=base,
                delta_qty=base_delta,
                price=px,
                trading_mode=trading_mode,
            )

            await OrderService._insert_ledger_entry(
                user_id=user_id,
                exchange_id=exchange_id,
                account_type=account_type,
                asset=base,
                delta=base_delta,
                ref_type="fill",
                ref_id=order_id,
                metadata={"symbol": symbol, "side": side, "price": str(px), "quantity": str(qty)},
                trading_mode=trading_mode,
            )

            await OrderService._insert_ledger_entry(
                user_id=user_id,
                exchange_id=exchange_id,
                account_type=account_type,
                asset=quote,
                delta=quote_delta,
                ref_type="fill",
                ref_id=order_id,
                metadata={"symbol": symbol, "side": side, "price": str(px), "quantity": str(qty)},
                trading_mode=trading_mode,
            )

            if fee_currency and fee_currency not in {base, quote} and fee_amount:
                await OrderService._insert_ledger_entry(
                    user_id=user_id,
                    exchange_id=exchange_id,
                    account_type=account_type,
                    asset=fee_currency,
                    delta=-fee_amount,
                    ref_type="fee",
                    ref_id=order_id,
                    metadata={"symbol": symbol, "side": side},
                    trading_mode=trading_mode,
                )

            await OrderService._update_simulation_balance(
                user_id=user_id,
                quote_asset=quote,
                delta=quote_delta,
                trading_mode=trading_mode,
            )

        else:
            qty = quantity if side == "buy" else -quantity
            await OrderService._upsert_position(
                user_id=user_id,
                exchange_id=exchange_id,
                account_type=account_type,
                instrument=symbol,
                delta_qty=qty,
                price=price,
                trading_mode=trading_mode,
            )

            if fee_currency and fee_amount:
                await OrderService._insert_ledger_entry(
                    user_id=user_id,
                    exchange_id=exchange_id,
                    account_type=account_type,
                    asset=fee_currency,
                    delta=-fee_amount,
                    ref_type="fee",
                    ref_id=order_id,
                    metadata={"symbol": symbol, "side": side},
                    trading_mode=trading_mode,
                )

    @staticmethod
    def _split_symbol(symbol: str) -> Tuple[Optional[str], Optional[str]]:
        if not symbol:
            return None, None
        for sep in ("/", "-", "_"):
            if sep in symbol:
                parts = symbol.split(sep)
                if len(parts) == 2:
                    return parts[0].strip(), parts[1].strip()
        common_quotes = ["USDT", "USDC", "BUSD", "USD", "BTC", "ETH"]
        for quote in common_quotes:
            if symbol.endswith(quote) and len(symbol) > len(quote):
                return symbol[: -len(quote)], quote
        return None, None

    @staticmethod
    async def _upsert_position(
        *,
        user_id: UUID,
        exchange_id: str,
        account_type: str,
        instrument: str,
        delta_qty: Decimal,
        price: Decimal,
        trading_mode: str,
    ) -> None:
        if not instrument:
            return

        table_name = 'paper_positions' if trading_mode == 'paper' else 'live_positions'
        pool = await get_pg_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT quantity, avg_price
                FROM {table_name}
                WHERE user_id = $1 AND exchange_id = $2 AND account_type = $3 AND instrument = $4
                """,
                user_id,
                exchange_id,
                account_type,
                instrument,
            )

            old_qty = Decimal(str(row["quantity"])) if row and row.get("quantity") is not None else Decimal('0')
            old_avg = Decimal(str(row["avg_price"])) if row and row.get("avg_price") is not None else None
            new_qty = old_qty + delta_qty

            new_avg: Optional[Decimal]
            if new_qty == 0:
                new_avg = None
            elif old_qty == 0 or old_avg is None:
                new_avg = price
            else:
                same_dir = (old_qty > 0 and delta_qty > 0) or (old_qty < 0 and delta_qty < 0)
                flipped = (old_qty > 0 > new_qty) or (old_qty < 0 < new_qty)
                if same_dir:
                    new_avg = ((abs(old_qty) * old_avg) + (abs(delta_qty) * price)) / abs(new_qty)
                elif flipped:
                    new_avg = price
                else:
                    new_avg = old_avg

            if row:
                await conn.execute(
                    f"""
                    UPDATE {table_name}
                    SET quantity = $1, avg_price = $2, updated_at = NOW()
                    WHERE user_id = $3 AND exchange_id = $4 AND account_type = $5 AND instrument = $6
                    """,
                    new_qty,
                    new_avg,
                    user_id,
                    exchange_id,
                    account_type,
                    instrument,
                )
            else:
                await conn.execute(
                    f"""
                    INSERT INTO {table_name} (user_id, exchange_id, account_type, instrument, quantity, avg_price, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    """,
                    user_id,
                    exchange_id,
                    account_type,
                    instrument,
                    new_qty,
                    new_avg,
                )

    @staticmethod
    async def _insert_ledger_entry(
        *,
        user_id: UUID,
        exchange_id: str,
        account_type: str,
        asset: str,
        delta: Decimal,
        ref_type: str,
        ref_id: UUID,
        metadata: Optional[Dict] = None,
        trading_mode: str,
    ) -> None:
        if not asset or delta == 0:
            return

        table_name = 'paper_ledger_entries' if trading_mode == 'paper' else 'live_ledger_entries'
        pool = await get_pg_pool()
        await pool.execute(
            f"""
            INSERT INTO {table_name} (user_id, exchange_id, account_type, asset, delta, ref_type, ref_id, metadata)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb)
            """,
            user_id,
            exchange_id,
            account_type,
            asset,
            delta,
            ref_type,
            ref_id,
            json.dumps(metadata or {}, ensure_ascii=False),
        )

    @staticmethod
    async def _update_simulation_balance(
        *,
        user_id: UUID,
        quote_asset: str,
        delta: Decimal,
        trading_mode: str,
    ) -> None:
        if trading_mode != 'paper' or delta == 0:
            return
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT quote_currency FROM simulation_config WHERE user_id = $1",
                user_id,
            )
            if not row:
                return
            if str(row["quote_currency"]) != str(quote_asset):
                return
            await conn.execute(
                """
                UPDATE simulation_config
                SET current_balance = current_balance + $2, updated_at = NOW()
                WHERE user_id = $1
                """,
                user_id,
                delta,
            )
    
    @staticmethod
    async def get_orders(
        user_id: Optional[UUID] = None,
        strategy_id: Optional[UUID] = None,
        exchange_id: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        account_type: Optional[str] = None,
        client_order_id: Optional[str] = None,
        plan_id: Optional[UUID] = None,
        leg_id: Optional[str] = None,
        external_order_id: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        trading_mode: str = 'paper',
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """查询订单列表"""
        table_name = 'paper_orders' if trading_mode == 'paper' else 'live_orders'
        
        pool = await get_pg_pool()
        
        try:
            where_clauses = []
            params = []
            param_idx = 1
            
            if user_id:
                where_clauses.append(f'user_id = ${param_idx}')
                params.append(user_id)
                param_idx += 1
            
            if strategy_id:
                where_clauses.append(f'strategy_id = ${param_idx}')
                params.append(strategy_id)
                param_idx += 1
            
            if exchange_id:
                where_clauses.append(f'exchange_id = ${param_idx}')
                params.append(exchange_id)
                param_idx += 1

            if symbol:
                where_clauses.append(f'symbol = ${param_idx}')
                params.append(symbol)
                param_idx += 1

            if status:
                where_clauses.append(f'status = ${param_idx}')
                params.append(status)
                param_idx += 1

            if account_type:
                where_clauses.append(f'account_type = ${param_idx}')
                params.append(account_type)
                param_idx += 1

            if client_order_id:
                where_clauses.append(f'client_order_id = ${param_idx}')
                params.append(client_order_id)
                param_idx += 1

            if plan_id:
                where_clauses.append(f'plan_id = ${param_idx}')
                params.append(plan_id)
                param_idx += 1

            if leg_id:
                where_clauses.append(f'leg_id = ${param_idx}')
                params.append(leg_id)
                param_idx += 1

            if external_order_id:
                where_clauses.append(f'external_order_id = ${param_idx}')
                params.append(external_order_id)
                param_idx += 1

            if created_after:
                where_clauses.append(f'created_at >= ${param_idx}')
                params.append(created_after)
                param_idx += 1

            if created_before:
                where_clauses.append(f'created_at <= ${param_idx}')
                params.append(created_before)
                param_idx += 1
            
            where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            
            query = f"""
                SELECT *
                FROM {table_name}
                {where_clause}
                ORDER BY created_at DESC
                LIMIT {limit}
                OFFSET {max(0, int(offset))}
            """
            
            rows = await pool.fetch(query, *params)
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"查询订单失败: {e}")
            return []

    @staticmethod
    async def get_fills(
        user_id: Optional[UUID] = None,
        exchange_id: Optional[str] = None,
        account_type: Optional[str] = None,
        symbol: Optional[str] = None,
        order_id: Optional[UUID] = None,
        order_ids: Optional[List[UUID]] = None,
        external_trade_id: Optional[str] = None,
        external_order_id: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        trading_mode: str = 'paper',
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict]:
        table_name = 'paper_fills' if trading_mode == 'paper' else 'live_fills'

        pool = await get_pg_pool()

        try:
            where_clauses = []
            params = []
            param_idx = 1

            if user_id:
                where_clauses.append(f'user_id = ${param_idx}')
                params.append(user_id)
                param_idx += 1

            if exchange_id:
                where_clauses.append(f'exchange_id = ${param_idx}')
                params.append(exchange_id)
                param_idx += 1

            if account_type:
                where_clauses.append(f'account_type = ${param_idx}')
                params.append(account_type)
                param_idx += 1

            if symbol:
                where_clauses.append(f'symbol = ${param_idx}')
                params.append(symbol)
                param_idx += 1

            if order_id:
                where_clauses.append(f'order_id = ${param_idx}')
                params.append(order_id)
                param_idx += 1

            if order_ids is not None:
                if len(order_ids) == 0:
                    return []
                where_clauses.append(f'order_id = ANY(${param_idx}::uuid[])')
                params.append(order_ids)
                param_idx += 1

            if external_trade_id:
                where_clauses.append(f'external_trade_id = ${param_idx}')
                params.append(external_trade_id)
                param_idx += 1

            if external_order_id:
                where_clauses.append(f'external_order_id = ${param_idx}')
                params.append(external_order_id)
                param_idx += 1

            if created_after:
                where_clauses.append(f'created_at >= ${param_idx}')
                params.append(created_after)
                param_idx += 1

            if created_before:
                where_clauses.append(f'created_at <= ${param_idx}')
                params.append(created_before)
                param_idx += 1

            where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            query = f"""
                SELECT *
                FROM {table_name}
                {where_clause}
                ORDER BY created_at DESC
                LIMIT {limit}
                OFFSET {max(0, int(offset))}
            """

            rows = await pool.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"查询成交失败: {e}")
            return []


class PnLService:
    """收益管理服务"""
    
    @staticmethod
    async def record_pnl(
        user_id: UUID,
        strategy_id: Optional[UUID],
        exchange_id: str,
        symbol: str,
        profit: Decimal,
        profit_rate: Optional[Decimal] = None,
        entry_price: Optional[Decimal] = None,
        exit_price: Optional[Decimal] = None,
        quantity: Optional[Decimal] = None,
        trading_mode: str = 'paper',
        metadata: Optional[Dict] = None
    ) -> UUID:
        """记录收益"""
        table_name = 'paper_pnl' if trading_mode == 'paper' else 'live_pnl'
        
        pool = await get_pg_pool()
        
        try:
            if profit_rate is None:
                profit_rate = None
                if entry_price and exit_price and entry_price > 0:
                    profit_rate = (exit_price - entry_price) / entry_price

            metadata_json = json.dumps(metadata or {}, ensure_ascii=False, default=str)
            
            pnl_id = await pool.fetchval(f"""
                INSERT INTO {table_name} (
                    user_id, strategy_id, exchange_id, symbol,
                    profit, profit_rate, entry_price, exit_price, quantity,
                    entry_time, exit_time, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW(), $10::jsonb)
                RETURNING id
            """, user_id, strategy_id, exchange_id, symbol,
                profit, profit_rate, entry_price, exit_price, quantity,
                metadata_json)
            
            logger.info(
                f"{'💰' if profit > 0 else '📉'} "
                f"收益已记录 ({trading_mode}): {float(profit):+.2f} USDT"
            )
            
            return pnl_id
            
        except Exception as e:
            logger.error(f"记录收益失败: {e}")
            raise
    
    @staticmethod
    async def get_total_profit(
        user_id: Optional[UUID] = None,
        strategy_id: Optional[UUID] = None,
        trading_mode: str = 'paper'
    ) -> Decimal:
        """获取总收益"""
        table_name = 'paper_pnl' if trading_mode == 'paper' else 'live_pnl'
        
        pool = await get_pg_pool()
        
        try:
            where_clauses = []
            params = []
            param_idx = 1
            
            if user_id:
                where_clauses.append(f'user_id = ${param_idx}')
                params.append(user_id)
                param_idx += 1
            
            if strategy_id:
                where_clauses.append(f'strategy_id = ${param_idx}')
                params.append(strategy_id)
                param_idx += 1
            
            where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            
            query = f"SELECT COALESCE(SUM(profit), 0) FROM {table_name} {where_clause}"
            
            total = await pool.fetchval(query, *params)
            return Decimal(str(total))
            
        except Exception as e:
            logger.error(f"获取总收益失败: {e}")
            return Decimal('0')
    
    @staticmethod
    async def get_statistics(
        user_id: Optional[UUID] = None,
        trading_mode: str = 'paper'
    ) -> Dict:
        """获取统计信息"""
        pool = await get_pg_pool()
        
        try:
            # 使用预定义的统计函数
            func_name = 'get_paper_stats' if trading_mode == 'paper' else 'get_live_stats'
            
            row = await pool.fetchrow(f"SELECT * FROM {func_name}($1)", user_id)
            
            return {
                'total_orders': int(row['total_orders']),
                'total_profit': float(row['total_profit']),
                'win_rate': float(row['win_rate']),
                'avg_profit': float(row['avg_profit']),
                'trading_mode': trading_mode
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                'total_orders': 0,
                'total_profit': 0.0,
                'win_rate': 0.0,
                'avg_profit': 0.0,
                'trading_mode': trading_mode
            }

    @staticmethod
    async def get_history(
        user_id: UUID,
        trading_mode: str = 'paper',
        exchange_id: Optional[str] = None,
        symbol: Optional[str] = None,
        plan_id: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict]:
        """获取收益明细"""
        table_name = 'paper_pnl' if trading_mode == 'paper' else 'live_pnl'
        pool = await get_pg_pool()

        try:
            where_clauses = ['user_id = $1']
            params: List = [user_id]
            param_idx = 2

            if exchange_id:
                where_clauses.append(f'exchange_id = ${param_idx}')
                params.append(exchange_id)
                param_idx += 1

            if symbol:
                where_clauses.append(f'symbol = ${param_idx}')
                params.append(symbol)
                param_idx += 1

            if plan_id:
                where_clauses.append(f"metadata->>'plan_id' = ${param_idx}")
                params.append(plan_id)
                param_idx += 1

            if created_after:
                where_clauses.append(f'created_at >= ${param_idx}')
                params.append(created_after)
                param_idx += 1

            if created_before:
                where_clauses.append(f'created_at <= ${param_idx}')
                params.append(created_before)
                param_idx += 1

            where_clause = f"WHERE {' AND '.join(where_clauses)}"

            query = f"""
                SELECT *
                FROM {table_name}
                {where_clause}
                ORDER BY created_at DESC
                LIMIT {limit}
                OFFSET {max(0, int(offset))}
            """

            rows = await pool.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取收益明细失败: {e}")
            return []
