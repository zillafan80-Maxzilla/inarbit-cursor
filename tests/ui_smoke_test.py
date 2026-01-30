import pytest
import httpx


@pytest.mark.asyncio
async def test_ui_homepage():
    """前端 UI 可达性与基本内容校验"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:5173/", timeout=5.0)
            if resp.status_code != 200:
                pytest.skip(f"UI 未启动: status={resp.status_code}")
            assert resp.text and len(resp.text) > 100
            assert "Inarbit" in resp.text or "inarbit" in resp.text.lower()
    except httpx.ConnectError:
        pytest.skip("UI 未启动")
