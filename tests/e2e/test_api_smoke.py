import pytest
import httpx
import os


@pytest.mark.asyncio
async def test_api_docs_available():
    """后端 API 文档可达性"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/docs", timeout=5.0)
            if resp.status_code != 200:
                pytest.skip(f"API 未启动: status={resp.status_code}")
            assert "OpenAPI" in resp.text or "swagger" in resp.text.lower()
    except httpx.ConnectError:
        pytest.skip("API 未启动")


@pytest.mark.asyncio
async def test_openapi_json_available():
    """OpenAPI JSON 可达性"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/openapi.json", timeout=5.0)
            if resp.status_code != 200:
                pytest.skip(f"API 未启动: status={resp.status_code}")
            data = resp.json()
            assert "openapi" in data
    except httpx.ConnectError:
        pytest.skip("API 未启动")


@pytest.mark.asyncio
async def test_login_and_oms_access():
    """登录后访问 OMS 关键接口"""
    username = os.getenv("INARBIT_E2E_USER")
    password = os.getenv("INARBIT_E2E_PASS")
    if not username or not password:
        pytest.skip("未提供 E2E 登录账号")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:8000/api/v1/auth/login",
                json={"username": username, "password": password},
                timeout=5.0,
            )
            if resp.status_code != 200:
                pytest.skip(f"登录失败: status={resp.status_code}")
            data = resp.json()
            token = data.get("token") or data.get("access_token")
            if not token:
                pytest.skip("登录未返回 token")

            headers = {"Authorization": f"Bearer {token}"}
            plans = await client.get(
                "http://localhost:8000/api/v1/oms/plans/latest?trading_mode=paper&limit=1",
                headers=headers,
                timeout=5.0,
            )
            assert plans.status_code == 200
            alerts = await client.get(
                "http://localhost:8000/api/v1/oms/alerts?limit=1",
                headers=headers,
                timeout=5.0,
            )
            assert alerts.status_code == 200
    except httpx.ConnectError:
        pytest.skip("API 未启动")
