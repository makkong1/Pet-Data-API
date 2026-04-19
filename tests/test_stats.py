import hashlib
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.core.config.settings.ADMIN_API_KEY_HASH", "different_hash")


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        mock = AsyncMock()
        mock.execute.return_value.mappings.return_value = []
        yield mock

    monkeypatch.setattr("app.core.database.AsyncSessionLocal", mock_session)


@pytest.mark.asyncio
async def test_stats_region_requires_auth(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/stats/region", headers={"X-API-Key": "bad"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_stats_trend_requires_auth(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/stats/trend?year=2024&month=1", headers={"X-API-Key": "bad"})
    assert response.status_code == 401
