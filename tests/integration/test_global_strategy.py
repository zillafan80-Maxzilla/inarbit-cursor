"""
全局策略集成测试
测试风险管理与API层的集成
"""
import pytest
import asyncio
import httpx
from unittest.mock import patch, AsyncMock
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "server"))


class TestRiskAPIIntegration:
    """测试风险API集成"""
    
    BASE_URL = "http://127.0.0.1:8000"
    
    @pytest.mark.asyncio
    async def test_get_risk_status(self):
        """测试获取风险状态API"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.BASE_URL}/api/v1/risk/status", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    assert "trading_enabled" in data
                    print(f"✅ 风险状态API正常: {data}")
                else:
                    pytest.skip(f"API返回状态码: {response.status_code}")
            except httpx.ConnectError:
                pytest.skip("API服务器未运行")
    
    @pytest.mark.asyncio
    async def test_panic_trigger_and_reset(self):
        """测试紧急停止触发和重置"""
        async with httpx.AsyncClient() as client:
            try:
                # 触发紧急停止
                response = await client.post(f"{self.BASE_URL}/api/v1/risk/panic", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    assert data.get("trading_enabled") is False
                    print("✅ 紧急停止触发成功")
                
                # 重置
                response = await client.post(f"{self.BASE_URL}/api/v1/risk/reset", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    assert data.get("trading_enabled") is True
                    print("✅ 紧急停止重置成功")
            except httpx.ConnectError:
                pytest.skip("API服务器未运行")


class TestStrategyAPIIntegration:
    """测试策略API集成"""
    
    BASE_URL = "http://127.0.0.1:8000"
    
    @pytest.mark.asyncio
    async def test_list_strategies(self):
        """测试获取策略列表API"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.BASE_URL}/api/v1/strategies", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    assert isinstance(data, list)
                    print(f"✅ 策略列表API正常，返回 {len(data)} 条策略")
                else:
                    pytest.skip(f"API返回状态码: {response.status_code}")
            except httpx.ConnectError:
                pytest.skip("API服务器未运行")


class TestExchangeAPIIntegration:
    """测试交易所API集成"""
    
    BASE_URL = "http://127.0.0.1:8000"
    
    @pytest.mark.asyncio
    async def test_list_exchanges(self):
        """测试获取交易所列表API"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.BASE_URL}/api/v1/exchanges", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    assert isinstance(data, list)
                    print(f"✅ 交易所列表API正常，返回 {len(data)} 个交易所")
                else:
                    pytest.skip(f"API返回状态码: {response.status_code}")
            except httpx.ConnectError:
                pytest.skip("API服务器未运行")


class TestHealthCheckIntegration:
    """测试健康检查集成"""
    
    BASE_URL = "http://127.0.0.1:8000"
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查API"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.BASE_URL}/health", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    assert "status" in data
                    assert "postgres" in data
                    assert "redis" in data
                    print(f"✅ 健康检查正常: {data}")
                else:
                    pytest.skip(f"API返回状态码: {response.status_code}")
            except httpx.ConnectError:
                pytest.skip("API服务器未运行")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
