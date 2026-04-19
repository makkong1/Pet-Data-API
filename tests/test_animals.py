import hashlib
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch


API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.core.config.settings.ADMIN_API_KEY_HASH", "different_hash")


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield AsyncMock()

    monkeypatch.setattr("app.core.database.AsyncSessionLocal", mock_session)


@pytest.mark.asyncio
async def test_list_animals_requires_api_key(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/animals")
    assert response.status_code == 422  # Header missing


@pytest.mark.asyncio
async def test_list_animals_invalid_key(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/animals", headers={"X-API-Key": "wrongkey"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_limit_max_100(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/animals?limit=200", headers=HEADERS)
    assert response.status_code == 422
