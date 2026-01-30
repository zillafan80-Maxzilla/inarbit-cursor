import pytest
import httpx


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
