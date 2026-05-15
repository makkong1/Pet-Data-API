"""Phase 1: /facilities/search 검증 — 파라미터 검증·인증·라우팅 우선순위만."""

import hashlib
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("app.platform.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.platform.core.config.settings.ADMIN_API_KEY_HASH", "different_hash")


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    @asynccontextmanager
    async def mock_session():
        mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        mock.execute.return_value = result_mock
        yield mock

    monkeypatch.setattr("app.platform.core.database.AsyncSessionLocal", mock_session)


@pytest.mark.asyncio
async def test_search_requires_api_key(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/facilities/search")
    assert response.status_code == 422  # missing X-API-Key header


@pytest.mark.asyncio
async def test_search_invalid_key_returns_401(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/facilities/search", headers={"X-API-Key": "bad"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_distance_requires_coords(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/facilities/search?sort=distance", headers=HEADERS)
    assert response.status_code == 400
    assert "lat" in response.json()["detail"]


@pytest.mark.asyncio
async def test_search_invalid_sort(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/facilities/search?sort=bogus", headers=HEADERS)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_search_default_returns_empty_items(mock_settings):
    """라우팅 우선순위: /facilities/search 가 /facilities/{int} 에 잡히지 않아야 함."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/facilities/search?q=강아지", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["sort"] == "name"
    assert data["has_next"] is False
