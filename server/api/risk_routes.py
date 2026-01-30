from fastapi import APIRouter, Depends
from typing import Dict, Any

router = APIRouter()

from ..risk_manager import RiskManager
from ..auth import CurrentUser, get_current_user, require_admin

_risk_managers: dict[str, RiskManager] = {}


def _get_user_risk_manager(user_id: str) -> RiskManager:
    rm = _risk_managers.get(user_id)
    if rm is None:
        rm = RiskManager(user_id=user_id)
        _risk_managers[user_id] = rm
    return rm

@router.get("/status")
async def get_risk_status(user: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    """返回当前风险检查结果"""
    rm = _get_user_risk_manager(str(user.id))
    allowed = await rm.check()
    return {"trading_allowed": allowed, "status": rm.get_status()}

@router.post("/panic")
async def trigger_panic(user: CurrentUser = Depends(get_current_user)):
    """手动触发紧急停止"""
    rm = _get_user_risk_manager(str(user.id))
    rm.panic_button.trigger()
    return {"status": "panic triggered"}

@router.post("/reset_panic")
async def reset_panic(user: CurrentUser = Depends(get_current_user)):
    """重置紧急停止状态"""
    rm = _get_user_risk_manager(str(user.id))
    rm.panic_button.reset()
    return {"status": "panic reset"}

@router.post("/reload_keys")
async def reload_api_keys(user: CurrentUser = Depends(get_current_user)):
    """手动触发 API 密钥热重载"""
    # 直接调用检查以触发加载逻辑
    rm = _get_user_risk_manager(str(user.id))
    await rm.api_key_reloader.check()
    return {"status": "api keys reloaded"}

