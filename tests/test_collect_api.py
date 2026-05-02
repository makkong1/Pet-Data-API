import hashlib
import pytest
from unittest.mock import AsyncMock, patch, ANY
from httpx import AsyncClient, ASGITransport
from app.main import app

ADMIN_KEY = "adminkey"
ADMIN_API_KEY_HASH = hashlib.sha256(ADMIN_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": ADMIN_KEY}


@pytest.fixture(autouse=True)
def patch_keys(monkeypatch):
    monkeypatch.setattr("app.platform.core.config.settings.API_KEY_HASH", "dummy")
    monkeypatch.setattr("app.platform.core.config.settings.ADMIN_API_KEY_HASH", ADMIN_API_KEY_HASH)


@pytest.mark.asyncio
async def test_collect_trigger_default_scope_facilities():
    mock_result = {"scope": "facilities", "facility_logs": []}
    with patch("app.serving.api.collect.run_collection_by_scope", new=AsyncMock(return_value=mock_result)) as mocked:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/collect/trigger", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["scope"] == "facilities"
    mocked.assert_awaited_once()


@pytest.mark.asyncio
async def test_collect_trigger_scope_trends():
    mock_result = {"scope": "trends", "trend_logs": []}
    with patch("app.serving.api.collect.run_collection_by_scope", new=AsyncMock(return_value=mock_result)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/collect/trigger?scope=trends", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["scope"] == "trends"


@pytest.mark.asyncio
async def test_collect_trigger_empty_scope_defaults_to_facilities():
    mock_result = {"scope": "facilities", "facility_logs": []}
    with patch("app.serving.api.collect.run_collection_by_scope", new=AsyncMock(return_value=mock_result)) as mocked:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/collect/trigger?scope=", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["scope"] == "facilities"
    mocked.assert_awaited_once_with(ANY, "facilities")


@pytest.mark.asyncio
async def test_collect_trigger_invalid_scope_validation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/collect/trigger?scope=bad", headers=HEADERS)
    assert response.status_code == 422
