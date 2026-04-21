import hashlib
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def patch_api_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.core.config.settings.ADMIN_API_KEY_HASH", "different_hash")


@pytest.mark.asyncio
async def test_get_trends_success():
    mock_keywords = [("오리젠", 10.0), ("로얄캐닌", 7.0)]
    mock_updated = "2026-04-21T03:05:00+00:00"

    with patch("app.api.trends.get_trend", new=AsyncMock(return_value=mock_keywords)), \
         patch("app.api.trends.get_updated_at", new=AsyncMock(return_value=mock_updated)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/trends/snack", headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "snack"
    assert data["keywords"][0]["keyword"] == "오리젠"
    assert data["keywords"][0]["score"] == 10


@pytest.mark.asyncio
async def test_get_trends_unknown_category():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/trends/unknown_cat", headers=HEADERS)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_trends_no_data_returns_503():
    with patch("app.api.trends.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.api.trends.get_updated_at", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/trends/snack", headers=HEADERS)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_get_trends_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/trends/snack")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_trends_limit_param():
    mock_keywords = [("오리젠", 10.0)]
    with patch("app.api.trends.get_trend", new=AsyncMock(return_value=mock_keywords)), \
         patch("app.api.trends.get_updated_at", new=AsyncMock(return_value="2026-04-21T03:05:00+00:00")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/trends/snack?limit=5", headers=HEADERS)
    assert response.status_code == 200
