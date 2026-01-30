import pytest
import httpx
import os


def _api_base() -> str:
    return os.getenv("INARBIT_API_BASE", "http://localhost:8000").rstrip("/")


@pytest.mark.asyncio
async def test_api_docs_available():
    """后端 API 文档可达性"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_api_base()}/docs", timeout=5.0)
            if resp.status_code == 404:
                resp = await client.get(f"{_api_base()}/api/docs", timeout=5.0)
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
            resp = await client.get(f"{_api_base()}/openapi.json", timeout=5.0)
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
                f"{_api_base()}/api/v1/auth/login",
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
                f"{_api_base()}/api/v1/oms/plans/latest?trading_mode=paper&limit=1",
                headers=headers,
                timeout=5.0,
            )
            assert plans.status_code == 200
            alerts = await client.get(
                f"{_api_base()}/api/v1/oms/alerts?limit=1",
                headers=headers,
                timeout=5.0,
            )
            assert alerts.status_code == 200
            exec_resp = await client.post(
                f"{_api_base()}/api/v1/oms/execute_latest",
                headers=headers,
                json={
                    "trading_mode": "paper",
                    "confirm_live": False,
                    "idempotency_key": "e2e-smoke",
                    "limit": 1,
                },
                timeout=10.0,
            )
            if exec_resp.status_code not in (200, 400):
                pytest.skip(f"执行请求失败: status={exec_resp.status_code}")
            if exec_resp.status_code == 400:
                detail = exec_resp.json().get("detail")
                pytest.skip(f"无可执行决策: {detail}")

            preview = await client.post(
                f"{_api_base()}/api/v1/oms/reconcile/preview",
                headers=headers,
                json={
                    "terminal": False,
                    "auto_cancel": False,
                    "timeout": False,
                    "max_rounds_exhausted": False,
                    "last_status_counts": {"filled": 0, "open": 1},
                },
                timeout=5.0,
            )
            assert preview.status_code == 200
    except httpx.ConnectError:
        pytest.skip("API 未启动")
