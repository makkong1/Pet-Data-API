import hashlib
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.core.config.settings.ADMIN_API_KEY_HASH", "different_hash")


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    @asynccontextmanager
    async def mock_session():
        mock = AsyncMock()
        mock.execute.return_value.mappings.return_value = []
        mock.execute.return_value.scalar_one_or_none.return_value = None
        yield mock

    monkeypatch.setattr("app.core.database.AsyncSessionLocal", mock_session)


@pytest.mark.asyncio
async def test_list_facilities_no_key(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/facilities")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_facilities_invalid_key(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/facilities", headers={"X-API-Key": "bad"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_facilities_limit_max(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/facilities?limit=200", headers=HEADERS)
    assert response.status_code == 422
