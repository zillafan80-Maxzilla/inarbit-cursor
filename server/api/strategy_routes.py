"""
策略管理 API 路由
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict
from uuid import UUID
import logging

from ..db import get_pg_pool
from ..auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/strategies", tags=["Strategies"])


@router.get("")
async def list_strategies(user: CurrentUser = Depends(get_current_user)) -> List[Dict]:
    """获取用户的所有策略配置"""
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    id,
                    strategy_type,
                    name,
                    description,
                    is_enabled,
                    priority,
                    config,
                    created_at,
                    updated_at
                FROM strategy_configs
                WHERE user_id = $1
                ORDER BY priority, created_at
            """, user.id)
            
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: UUID, user: CurrentUser = Depends(get_current_user)) -> Dict:
    """获取单个策略详情"""
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    id,
                    strategy_type,
                    name,
                    description,
                    is_enabled,
                    priority,
                    config,
                    created_at,
                    updated_at
                FROM strategy_configs
                WHERE id = $1 AND user_id = $2
            """, strategy_id, user.id)
            
            if not row:
                raise HTTPException(status_code=404, detail="策略不存在")
            
            return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取策略详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: UUID, user: CurrentUser = Depends(get_current_user)) -> Dict:
    """启用/禁用策略"""
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            # 获取当前状态
            current = await conn.fetchval("""
                SELECT is_enabled FROM strategy_configs 
                WHERE id = $1 AND user_id = $2
            """, strategy_id, user.id)
            
            if current is None:
                raise HTTPException(status_code=404, detail="策略不存在")
            
            # 切换状态
            new_state = not current
            await conn.execute("""
                UPDATE strategy_configs 
                SET is_enabled = $1, updated_at = NOW()
                WHERE id = $2 AND user_id = $3
            """, new_state, strategy_id, user.id)
            
            return {"success": True, "is_enabled": new_state}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换策略状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{strategy_id}/update")
async def update_strategy(
    strategy_id: UUID, 
    config: Dict,
    user: CurrentUser = Depends(get_current_user)
) -> Dict:
    """更新策略配置"""
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE strategy_configs 
                SET config = $1::jsonb, updated_at = NOW()
                WHERE id = $2 AND user_id = $3
            """, config, strategy_id, user.id)
            
            return {"success": True, "message": "策略配置已更新"}
    except Exception as e:
        logger.error(f"更新策略配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_strategies(user: CurrentUser = Depends(get_current_user)) -> Dict:
    """重新加载策略配置"""
    # 这是一个占位符，实际可能需要通知策略引擎重新加载
    return {"success": True, "message": "策略配置已重新加载"}
