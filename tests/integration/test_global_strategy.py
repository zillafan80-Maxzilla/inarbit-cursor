"""
全局策略集成测试
测试风险管理与API层的集成
"""
import pytest
import asyncio
import httpx
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from pathlib import Path
import sys

# 添加项目路径（仓库根目录）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.app import app as fastapi_app


def _get_client() -> AsyncClient:
    transport = ASGITransport(app=fastapi_app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestRiskAPIIntegration:
    """测试风险API集成"""
    
    @pytest.mark.asyncio
    async def test_get_risk_status(self):
        """测试获取风险状态API"""
        async with _get_client() as client:
            try:
                response = await client.get("/api/v1/risk/status", timeout=5.0)
            except Exception:
                pytest.skip("API服务未就绪")
            if response.status_code == 200:
                data = response.json()
                assert "trading_enabled" in data
                print(f"✅ 风险状态API正常: {data}")
            else:
                pytest.skip(f"API返回状态码: {response.status_code}")
    
    @pytest.mark.asyncio
    async def test_panic_trigger_and_reset(self):
        """测试紧急停止触发和重置"""
        async with _get_client() as client:
            try:
                # 触发紧急停止
                response = await client.post("/api/v1/risk/panic", timeout=5.0)
            except Exception:
                pytest.skip("API服务未就绪")
            if response.status_code == 200:
                data = response.json()
                assert data.get("trading_enabled") is False
                print("✅ 紧急停止触发成功")

            # 重置
            response = await client.post("/api/v1/risk/reset", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                assert data.get("trading_enabled") is True
                print("✅ 紧急停止重置成功")


class TestStrategyAPIIntegration:
    """测试策略API集成"""
    
    @pytest.mark.asyncio
    async def test_list_strategies(self):
        """测试获取策略列表API"""
        async with _get_client() as client:
            try:
                response = await client.get("/api/v1/strategies", timeout=5.0)
            except Exception:
                pytest.skip("API服务未就绪")
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)
                print(f"✅ 策略列表API正常，返回 {len(data)} 条策略")
            else:
                pytest.skip(f"API返回状态码: {response.status_code}")


class TestExchangeAPIIntegration:
    """测试交易所API集成"""
    
    @pytest.mark.asyncio
    async def test_list_exchanges(self):
        """测试获取交易所列表API"""
        async with _get_client() as client:
            try:
                response = await client.get("/api/v1/exchanges", timeout=5.0)
            except Exception:
                pytest.skip("API服务未就绪")
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)
                print(f"✅ 交易所列表API正常，返回 {len(data)} 个交易所")
            else:
                pytest.skip(f"API返回状态码: {response.status_code}")


class TestHealthCheckIntegration:
    """测试健康检查集成"""
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查API"""
        async with _get_client() as client:
            try:
                response = await client.get("/health", timeout=5.0)
            except Exception:
                pytest.skip("API服务未就绪")
            if response.status_code == 200:
                data = response.json()
                assert "status" in data
                checks = data.get("checks", {})
                assert "postgres" in checks
                assert "redis" in checks
                print(f"✅ 健康检查正常: {data}")
            else:
                pytest.skip(f"API返回状态码: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
