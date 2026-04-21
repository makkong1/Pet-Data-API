import hashlib
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}

VALID_PAYLOAD = {
    "lat": 37.5665,
    "lng": 126.9780,
    "context": "grooming",
    "radius_km": 3.0,
    "top_n": 5,
    "pet": {"type": "dog", "breed": "말티즈", "age": "2살"},
}


@pytest.fixture(autouse=True)
def patch_api_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.core.config.settings.ADMIN_API_KEY_HASH", "different")


@pytest.mark.asyncio
async def test_recommend_success():
    mock_facilities = [{"name": "해피독", "distance_m": 320, "address": "서울"}]
    mock_trends = [("스포팅컷", 41.0), ("여름컷", 35.0)]
    mock_reco = "말티즈에게는 스포팅컷이 인기입니다."

    with patch("app.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_facilities)), \
         patch("app.api.recommend.get_trend", new=AsyncMock(return_value=mock_trends)), \
         patch("app.api.recommend.generate_recommendation", new=AsyncMock(return_value=mock_reco)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["context"] == "grooming"
    assert data["facilities"][0]["name"] == "해피독"
    assert data["trends"][0]["keyword"] == "스포팅컷"
    assert data["recommendation"] == mock_reco


@pytest.mark.asyncio
async def test_recommend_ollama_down_still_returns_data():
    mock_facilities = [{"name": "해피독", "distance_m": 320, "address": "서울"}]

    with patch("app.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_facilities)), \
         patch("app.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.api.recommend.generate_recommendation", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["recommendation"] is None
    assert len(data["facilities"]) == 1


@pytest.mark.asyncio
async def test_recommend_invalid_context():
    payload = {**VALID_PAYLOAD, "context": "unknown"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/recommend", json=payload, headers=HEADERS)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_recommend_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/recommend", json=VALID_PAYLOAD)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recommend_no_pet():
    payload = {**VALID_PAYLOAD, "pet": None}
    with patch("app.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=[])), \
         patch("app.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.api.recommend.generate_recommendation", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=payload, headers=HEADERS)
    assert response.status_code == 200
