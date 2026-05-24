import hashlib
import json

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def patch_api_key(monkeypatch):
    monkeypatch.setattr("app.platform.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.platform.core.config.settings.ADMIN_API_KEY_HASH", "different_admin_hash")


@pytest.mark.asyncio
async def test_get_popular_returns_data():
    data = [{"name": "해피독", "mention_count": 5, "avg_freshness": 0.8, "score": 1.0}]
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(data, ensure_ascii=False))

    with patch("app.serving.api.popular.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/popular/grooming", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()[0]["name"] == "해피독"


@pytest.mark.asyncio
async def test_get_popular_unknown_context_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/popular/unknown_xyz", headers=HEADERS)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_popular_redis_miss_503():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("app.serving.api.popular.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/popular/grooming", headers=HEADERS)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_get_popular_alias_snack_reads_supplies_key():
    data = [{"name": "사료왕", "mention_count": 3, "avg_freshness": 0.7, "score": 1.0}]
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(data, ensure_ascii=False))

    with patch("app.serving.api.popular.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/popular/snack", headers=HEADERS)
    assert response.status_code == 200
    mock_redis.get.assert_called_once_with("popular:supplies")


@pytest.mark.asyncio
async def test_get_popular_limit_param():
    data = [
        {
            "name": f"샵{i}",
            "mention_count": 10 - i,
            "avg_freshness": 0.8,
            "score": round(1.0 - i * 0.05, 4),
        }
        for i in range(10)
    ]
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(data, ensure_ascii=False))

    with patch("app.serving.api.popular.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/popular/grooming?limit=3", headers=HEADERS)

    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.asyncio
async def test_get_popular_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/popular/grooming")
    assert response.status_code == 401
    assert response.json().get("detail") == "Missing X-API-Key header"
