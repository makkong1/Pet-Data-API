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
    monkeypatch.setattr("app.platform.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.platform.core.config.settings.ADMIN_API_KEY_HASH", "different")


@pytest.mark.asyncio
async def test_recommend_success():
    mock_facilities = [{"name": "해피독", "distance_m": 320, "address": "서울"}]
    mock_trends = [("스포팅컷", 41.0), ("여름컷", 35.0)]
    mock_reco = "말티즈에게는 스포팅컷이 인기입니다."

    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_facilities)), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=mock_trends)), \
         patch("app.serving.api.recommend.generate_recommendation", new=AsyncMock(return_value=mock_reco)):
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

    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_facilities)), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.generate_recommendation", new=AsyncMock(return_value=None)):
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
    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.generate_recommendation", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=payload, headers=HEADERS)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_recommend_supplies_legacy_context_uses_trend_only():
    payload = {**VALID_PAYLOAD, "context": "snack"}
    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(side_effect=[
             [("용품점", 10.0)],
             [("오리젠", 7.0)],
             [("로얄캐닌", 5.0)],
             [("의류", 1.0)],
         ])), \
         patch("app.serving.api.recommend.generate_recommendation", new=AsyncMock(return_value="must_not_use")) as mock_llm:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=payload, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["context"] == "snack"
    mock_llm.assert_not_called()
    assert data["recommendation"] is not None
    assert "인기 키워드" in data["recommendation"]
    assert "용품점" in data["recommendation"] or "오리젠" in data["recommendation"]
    assert len(data["facilities"]) == 0
    assert len(data["trends"]) >= 1


# ────────── 그루밍 MVP 회귀 테스트 (§3.1) ──────────

@pytest.mark.asyncio
async def test_hospital_context_uses_legacy_pipe():
    """hospital 컨텍스트는 항상 레거시 파이프 → recommend_version='legacy'."""
    payload = {**VALID_PAYLOAD, "context": "hospital"}
    mock_facilities = [{"source_id": "H001", "name": "행복동물병원", "distance_m": 500, "address": "서울", "lat": 37.5, "lng": 126.9}]

    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_facilities)), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.generate_recommendation", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=payload, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["recommend_version"] == "legacy"
    fac = data["facilities"][0]
    assert fac["mention_count"] == 0
    assert fac["mention_score"] == 0.0
    assert fac["source"] == "public"
    assert fac["score"] == 0.0


@pytest.mark.asyncio
async def test_grooming_flag_off_uses_legacy_pipe(monkeypatch):
    """GROOMING_MVP_ENABLED=false 이면 grooming도 레거시 파이프."""
    monkeypatch.setattr("app.serving.api.recommend.settings", type("S", (), {
        "GROOMING_MVP_ENABLED": False
    })())
    mock_facilities = [{"source_id": "B001", "name": "해피독", "distance_m": 100, "address": "서울", "lat": 37.5665, "lng": 126.979}]

    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_facilities)), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.generate_recommendation", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["recommend_version"] == "legacy"


@pytest.mark.asyncio
async def test_grooming_flag_on_uses_mvp_pipe(monkeypatch):
    """GROOMING_MVP_ENABLED=true + context=grooming → grooming-mvp-v1."""
    monkeypatch.setattr("app.serving.api.recommend.settings", type("S", (), {
        "GROOMING_MVP_ENABLED": True
    })())

    mock_public = [{"source_id": "B001", "name": "해피독", "address": "서울", "lat": 37.5665, "lng": 126.979, "distance_m": 100}]
    mock_mention_map = {"해피독": {"count": 3, "freshness": 0.8}}

    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_public)), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.extract_grooming_mentions",
               new=AsyncMock(return_value=(mock_mention_map, list(mock_mention_map.keys())))), \
         patch("app.serving.api.recommend.search_kakao_places", new=AsyncMock(return_value={})):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["recommend_version"] == "grooming-mvp-v1"
    fac = data["facilities"][0]
    assert fac["mention_count"] == 3
    assert fac["source"] in ("public", "public+kakao")
    assert 0.0 <= fac["score"] <= 1.0
    assert 0.0 <= fac["mention_score"] <= 1.0
    assert data["recommendation"] is not None


@pytest.mark.asyncio
async def test_grooming_mvp_blog_failure_fallback(monkeypatch):
    """블로그 실패 시 mention=0으로 폴백, HTTP 200 유지."""
    monkeypatch.setattr("app.serving.api.recommend.settings", type("S", (), {
        "GROOMING_MVP_ENABLED": True
    })())

    mock_public = [{"source_id": "B001", "name": "해피독", "address": "서울", "lat": 37.5665, "lng": 126.979, "distance_m": 100}]

    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_public)), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.extract_grooming_mentions",
               new=AsyncMock(side_effect=Exception("naver down"))), \
         patch("app.serving.api.recommend.search_kakao_places", new=AsyncMock(return_value={})):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["recommend_version"] == "grooming-mvp-v1"
    assert data["facilities"][0]["mention_count"] == 0


@pytest.mark.asyncio
async def test_grooming_mvp_kakao_failure_fallback(monkeypatch):
    """Kakao 실패 시 공공 DB만으로 응답, HTTP 200 유지."""
    monkeypatch.setattr("app.serving.api.recommend.settings", type("S", (), {
        "GROOMING_MVP_ENABLED": True
    })())

    mock_public = [{"source_id": "B001", "name": "해피독", "address": "서울", "lat": 37.5665, "lng": 126.979, "distance_m": 100}]

    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_public)), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.extract_grooming_mentions",
               new=AsyncMock(return_value=({}, []))), \
         patch("app.serving.api.recommend.search_kakao_places",
               new=AsyncMock(side_effect=Exception("kakao down"))):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["recommend_version"] == "grooming-mvp-v1"
    assert data["facilities"][0]["source"] == "public"
