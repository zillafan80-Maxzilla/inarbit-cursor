"""
风险管理器单元测试
测试 RiskManager 及其子模块的功能
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
import sys
import os

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from risk_manager import (
    RiskManager,
    TotalEquityMonitor,
    MaxDrawdownCircuitBreaker,
    ExposureLimiter,
    Rebalancer,
    FundingRateMonitor,
    AutoTransfer,
    PanicButton,
    ApiKeyHotReloader,
)


class TestTotalEquityMonitor:
    """测试总权益监控模块"""
    
    @pytest.mark.asyncio
    async def test_check_above_threshold(self):
        """测试权益高于阈值时返回True"""
        monitor = TotalEquityMonitor({"threshold": 50000.0})
        # 模拟返回高于阈值的权益
        with patch.object(monitor, '_fetch_equity', new_callable=AsyncMock, return_value=100000.0):
            result = await monitor.check()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_below_threshold(self):
        """测试权益低于阈值时返回False"""
        monitor = TotalEquityMonitor({"threshold": 150000.0})
        with patch.object(monitor, '_fetch_equity', new_callable=AsyncMock, return_value=100000.0):
            result = await monitor.check()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_check_no_threshold(self):
        """测试未设置阈值时返回True"""
        monitor = TotalEquityMonitor({})
        result = await monitor.check()
        assert result is True


class TestMaxDrawdownCircuitBreaker:
    """测试最大回撤熔断模块"""
    
    @pytest.mark.asyncio
    async def test_check_within_limit(self):
        """测试回撤在限制内时返回True"""
        cb = MaxDrawdownCircuitBreaker({
            "max_drawdown": 0.2,
            "peak_equity": 100000.0
        })
        # 模拟10%回撤
        with patch.object(cb, '_fetch_equity', new_callable=AsyncMock, return_value=90000.0):
            result = await cb.check()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_exceeds_limit(self):
        """测试回撤超过限制时返回False"""
        cb = MaxDrawdownCircuitBreaker({
            "max_drawdown": 0.2,
            "peak_equity": 100000.0
        })
        # 模拟30%回撤
        with patch.object(cb, '_fetch_equity', new_callable=AsyncMock, return_value=70000.0):
            result = await cb.check()
        assert result is False


class TestExposureLimiter:
    """测试敞口限制模块"""
    
    @pytest.mark.asyncio
    async def test_check_within_limit(self):
        """测试敞口在限制内"""
        limiter = ExposureLimiter({"limit": 0.3})
        result = await limiter.check()  # 默认敞口是0.25
        assert result is True


class TestRebalancer:
    """测试跨所平衡模块"""
    
    @pytest.mark.asyncio
    async def test_check_enabled(self):
        """测试启用时返回True"""
        rebalancer = Rebalancer({"enabled": True})
        result = await rebalancer.check()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_disabled(self):
        """测试禁用时返回True"""
        rebalancer = Rebalancer({"enabled": False})
        result = await rebalancer.check()
        assert result is True


class TestFundingRateMonitor:
    """测试资金费率监控模块"""
    
    @pytest.mark.asyncio
    async def test_check_normal_rate(self):
        """测试正常费率时返回True"""
        monitor = FundingRateMonitor({"max_rate": 0.01})
        result = await monitor.check()  # 默认费率是0.005
        assert result is True


class TestPanicButton:
    """测试紧急停止按钮模块"""
    
    @pytest.mark.asyncio
    async def test_check_not_triggered(self):
        """测试未触发时返回True"""
        panic = PanicButton({})
        result = await panic.check()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_triggered(self):
        """测试触发后返回False"""
        panic = PanicButton({})
        panic.trigger()
        result = await panic.check()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_reset(self):
        """测试重置功能"""
        panic = PanicButton({})
        panic.trigger()
        panic.reset()
        result = await panic.check()
        assert result is True


class TestAutoTransfer:
    """测试自动划转模块"""
    
    @pytest.mark.asyncio
    async def test_check_mock_mode(self):
        """测试mock模式返回True"""
        transfer = AutoTransfer({"mode": "mock"})
        result = await transfer.check()
        assert result is True


class TestApiKeyHotReloader:
    """测试API密钥热重载模块"""
    
    @pytest.mark.asyncio
    async def test_check_file_not_exists(self):
        """测试文件不存在时返回True"""
        reloader = ApiKeyHotReloader({"watch_path": "/nonexistent/path"})
        result = await reloader.check()
        assert result is True


class TestRiskManager:
    """测试风险管理器主类"""
    
    @pytest.mark.asyncio
    async def test_check_all_pass(self):
        """测试所有检查通过时返回True"""
        rm = RiskManager()
        # 模拟所有子模块检查通过
        with patch.object(rm.total_equity_monitor, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.max_drawdown_cb, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.exposure_limiter, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.rebalancer, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.funding_rate_monitor, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.auto_transfer, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.panic_button, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.api_key_reloader, 'check', new_callable=AsyncMock, return_value=True):
            result = await rm.check()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_one_fail(self):
        """测试任一检查失败时返回False"""
        rm = RiskManager()
        with patch.object(rm.total_equity_monitor, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.max_drawdown_cb, 'check', new_callable=AsyncMock, return_value=False), \
             patch.object(rm.exposure_limiter, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.rebalancer, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.funding_rate_monitor, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.auto_transfer, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.panic_button, 'check', new_callable=AsyncMock, return_value=True), \
             patch.object(rm.api_key_reloader, 'check', new_callable=AsyncMock, return_value=True):
            result = await rm.check()
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
