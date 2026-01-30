import pytest
from uuid import uuid4

from server.services import oms_service
from server.services.oms_service import OmsService


class _DummyConn:
    async def execute(self, *args, **kwargs):
        return None


class _DummyAcquire:
    async def __aenter__(self):
        return _DummyConn()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyPool:
    def acquire(self):
        return _DummyAcquire()


@pytest.mark.asyncio
async def test_update_execution_plan_updates_opportunity_status(monkeypatch):
    service = OmsService()
    plan_id = uuid4()
    opp_id = uuid4()

    async def _fake_get_pool():
        return _DummyPool()

    async def _fake_get_opportunity_id(*, plan_id, trading_mode):
        return opp_id

    updated = {}

    async def _fake_update_opportunity_status(*, opportunity_id, trading_mode, status, decision_reason=None):
        updated["opportunity_id"] = opportunity_id
        updated["trading_mode"] = trading_mode
        updated["status"] = status

    monkeypatch.setattr(oms_service, "get_pg_pool", _fake_get_pool)
    monkeypatch.setattr(service, "_get_execution_plan_opportunity_id", _fake_get_opportunity_id)
    monkeypatch.setattr(service, "_update_opportunity_status", _fake_update_opportunity_status)

    await service._update_execution_plan(plan_id=plan_id, trading_mode="paper", status="completed")
    assert updated["opportunity_id"] == opp_id
    assert updated["trading_mode"] == "paper"
    assert updated["status"] == "executed"


@pytest.mark.asyncio
async def test_update_execution_plan_rejects_on_failure(monkeypatch):
    service = OmsService()
    plan_id = uuid4()
    opp_id = uuid4()

    async def _fake_get_pool():
        return _DummyPool()

    async def _fake_get_opportunity_id(*, plan_id, trading_mode):
        return opp_id

    updated = {}

    async def _fake_update_opportunity_status(*, opportunity_id, trading_mode, status, decision_reason=None):
        updated["status"] = status

    monkeypatch.setattr(oms_service, "get_pg_pool", _fake_get_pool)
    monkeypatch.setattr(service, "_get_execution_plan_opportunity_id", _fake_get_opportunity_id)
    monkeypatch.setattr(service, "_update_opportunity_status", _fake_update_opportunity_status)

    await service._update_execution_plan(plan_id=plan_id, trading_mode="paper", status="failed")
    assert updated["status"] == "rejected"
