import json
import logging
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.decision_service import DecisionService, RiskConstraints
from ..services import get_decision_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/decision", tags=["decision"])


class RiskConstraintsRequest(BaseModel):
    max_exposure_per_symbol: Optional[float] = Field(None, description="单币种最大敞口（USDT）")
    max_total_exposure: Optional[float] = Field(None, description="总敞口上限")
    min_profit_rate: Optional[float] = Field(None, description="最小收益率阈值")
    max_positions: Optional[int] = Field(None, description="最大同时持仓数")
    blacklist_symbols: Optional[List[str]] = Field(None, description="黑名单币种")
    whitelist_symbols: Optional[List[str]] = Field(None, description="白名单币种（若非空则只选这些）")
    max_drawdown_per_symbol: Optional[float] = Field(None, description="单币种最大回撤")
    liquidity_score_min: Optional[float] = Field(None, description="最小流动性评分")
    max_spread_rate: Optional[float] = Field(None, description="最大允许点差比例（ask-bid)/mid")
    max_data_age_ms: Optional[int] = Field(None, description="数据最大允许延迟（ms）")
    min_confidence: Optional[float] = Field(None, description="最小置信度阈值")
    max_abs_funding_rate: Optional[float] = Field(None, description="资金费率绝对值上限")


class DecisionResponse(BaseModel):
    strategy_type: str = Field(..., alias="strategyType")
    exchange_id: str = Field(..., alias="exchange")
    symbol: str
    direction: str
    expected_profit_rate: float = Field(..., alias="expectedProfitRate")
    estimated_exposure: float = Field(..., alias="estimatedExposure")
    risk_score: float = Field(..., alias="riskScore")
    confidence: float
    timestamp_ms: int = Field(..., alias="timestamp")
    raw_opportunity: dict = Field(..., alias="rawOpportunity")

    class Config:
        validate_by_name = True


@router.get("/constraints", summary="获取当前避险约束配置")
async def get_constraints(
    decision_service: DecisionService = Depends(get_decision_service),
):
    """返回当前决策器使用的避险约束配置"""
    c = decision_service._constraints
    return {
        "max_exposure_per_symbol": float(c.max_exposure_per_symbol),
        "max_total_exposure": float(c.max_total_exposure),
        "min_profit_rate": float(c.min_profit_rate),
        "max_positions": c.max_positions,
        "blacklist_symbols": list(c.blacklist_symbols),
        "whitelist_symbols": list(c.whitelist_symbols),
        "max_drawdown_per_symbol": float(c.max_drawdown_per_symbol),
        "liquidity_score_min": float(c.liquidity_score_min),
        "max_spread_rate": float(c.max_spread_rate),
        "max_data_age_ms": int(c.max_data_age_ms),
        "min_confidence": float(c.min_confidence),
        "max_abs_funding_rate": float(c.max_abs_funding_rate),
    }


@router.get("/constraints/auto", summary="获取机器人动态约束（overlay）")
async def get_auto_constraints():
    from ..db import get_redis
    redis = await get_redis()
    raw = await redis.get("decision:constraints:auto")
    return json.loads(raw) if raw else {}


@router.get("/constraints/effective", summary="获取生效中的约束（human+auto 合并后）")
async def get_effective_constraints():
    from ..db import get_redis
    redis = await get_redis()
    raw = await redis.get("decision:constraints:effective")
    return json.loads(raw) if raw else {}


@router.post("/constraints", summary="更新避险约束配置")
async def update_constraints(
    req: RiskConstraintsRequest,
    decision_service: DecisionService = Depends(get_decision_service),
):
    """动态更新决策器的避险约束（支持运行时修改）"""
    payload = {k: v for k, v in req.dict(exclude_unset=True).items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="至少需要提供一个约束参数")
    await decision_service.update_constraints(**payload)
    return {"message": "约束配置已更新", "updated": payload}


@router.get("/decisions", summary="获取当前决策列表")
async def get_decisions(
    limit: int = Query(10, ge=1, le=50, description="返回决策数量上限"),
    decision_service: DecisionService = Depends(get_decision_service),
):
    """从 Redis 读取当前决策器产出的决策列表（按风险评分升序）"""
    from ..db import get_redis
    redis = await get_redis()
    members = await redis.zrange("decisions:latest", 0, limit - 1, withscores=True)
    result = []
    for member, score in members:
        try:
            data = json.loads(member)
            result.append(DecisionResponse(**data))
        except Exception:
            continue
    return {"decisions": result}


@router.post("/decisions/clear", summary="清空当前决策列表")
async def clear_decisions(
    decision_service: DecisionService = Depends(get_decision_service),
):
    """清空 Redis 中的决策列表（用于重置或紧急停止）"""
    from ..db import get_redis
    redis = await get_redis()
    await redis.delete("decisions:latest")
    return {"message": "决策列表已清空"}
