"""
用户管理 API 路由
包含邮件简报配置
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging

from ..db import get_pg_pool
from ..auth import CurrentUser, get_current_user
from ..services.email_report_service import get_email_report_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/user", tags=["User Management"])


class EmailReportConfig(BaseModel):
    """邮件简报配置"""
    enabled: bool
    email: EmailStr
    report_time: str = "09:00"  # 格式: HH:MM


@router.get("/email-report/config")
async def get_email_report_config(user: CurrentUser = Depends(get_current_user)):
    """获取邮件简报配置"""
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            config = await conn.fetchrow("""
                SELECT 
                    gs.email_report_enabled,
                    gs.email_report_time,
                    u.email
                FROM global_settings gs
                JOIN users u ON u.id = gs.user_id
                WHERE gs.user_id = $1
            """, user.id)
            
            if not config:
                return {
                    "enabled": False,
                    "email": user.email or "",
                    "report_time": "09:00"
                }
            
            return {
                "enabled": config['email_report_enabled'] or False,
                "email": config['email'] or "",
                "report_time": config['email_report_time'] or "09:00"
            }
    except Exception as e:
        logger.error(f"获取邮件简报配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/email-report/config")
async def update_email_report_config(
    config: EmailReportConfig,
    user: CurrentUser = Depends(get_current_user)
):
    """更新邮件简报配置"""
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            # 更新用户邮箱
            await conn.execute("""
                UPDATE users 
                SET email = $1 
                WHERE id = $2
            """, config.email, user.id)
            
            # 更新简报配置
            await conn.execute("""
                INSERT INTO global_settings (
                    user_id, 
                    email_report_enabled, 
                    email_report_time
                ) VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE
                SET email_report_enabled = EXCLUDED.email_report_enabled,
                    email_report_time = EXCLUDED.email_report_time
            """, user.id, config.enabled, config.report_time)
            
            return {"success": True, "message": "邮件简报配置已更新"}
    except Exception as e:
        logger.error(f"更新邮件简报配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/email-report/test")
async def send_test_email_report(user: CurrentUser = Depends(get_current_user)):
    """发送测试邮件"""
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            email = await conn.fetchval("""
                SELECT email FROM users WHERE id = $1
            """, user.id)
            
            if not email:
                raise HTTPException(status_code=400, detail="请先配置邮箱地址")
        
        service = await get_email_report_service()
        success = await service.send_test_email(user.id, email)
        
        if success:
            return {"success": True, "message": f"测试邮件已发送到 {email}"}
        else:
            raise HTTPException(status_code=500, detail="发送失败，请检查SMTP配置")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发送测试邮件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
