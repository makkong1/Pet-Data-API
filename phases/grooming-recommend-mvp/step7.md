# Step 7 — 회귀 테스트

## 목적
비그루밍 컨텍스트와 플래그 off 시 기존 계약이 깨지지 않음을 테스트로 고정하고, 플래그 on 시 그루밍 MVP 응답 형태를 검증한다.

## 배경
- SSOT: `docs/GROOMING-RECOMMEND-MVP.md` §3.1, §2.6
- 기존 `tests/test_recommend_api.py`를 확장한다. 기존 테스트는 수정하지 않는다.

## 추가할 테스트: `tests/test_recommend_api.py` 하단에 append

```python
# ────────── 그루밍 MVP 회귀 테스트 (§3.1) ──────────

@pytest.mark.asyncio
async def test_hospital_context_uses_legacy_pipe():
    """hospital 컨텍스트는 항상 레거시 파이프 → recommend_version='legacy'."""
    payload = {**VALID_PAYLOAD, "context": "hospital"}
    mock_facilities = [{"name": "행복동물병원", "distance_m": 500, "address": "서울", "source_id": "H001"}]

    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_facilities)), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.generate_recommendation", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=payload, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["recommend_version"] == "legacy"
    fac = data["facilities"][0]
    # 신규 필드 기본값 존재
    assert fac["mention_count"] == 0
    assert fac["mention_score"] == 0.0
    assert fac["source"] == "public"
    assert fac["score"] == 0.0


@pytest.mark.asyncio
async def test_grooming_flag_off_uses_legacy_pipe(monkeypatch):
    """GROOMING_MVP_ENABLED=false 이면 grooming도 레거시 파이프."""
    monkeypatch.setattr("app.platform.core.config.settings.GROOMING_MVP_ENABLED", False)
    mock_facilities = [{"name": "해피독", "distance_m": 100, "address": "서울", "source_id": "B001"}]

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
    monkeypatch.setattr("app.platform.core.config.settings.GROOMING_MVP_ENABLED", True)

    mock_public = [{"source_id": "B001", "name": "해피독", "address": "서울", "lat": 37.5665, "lng": 126.979, "distance_m": 100}]
    mock_mention_map = {"해피독": {"count": 3, "freshness": 0.8}}
    mock_kakao_map = {}

    with patch("app.serving.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_public)), \
         patch("app.serving.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.serving.api.recommend.extract_grooming_mentions",
               new=AsyncMock(return_value=(mock_mention_map, list(mock_mention_map.keys())))), \
         patch("app.serving.api.recommend.search_kakao_places", new=AsyncMock(return_value=mock_kakao_map)):
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
    monkeypatch.setattr("app.platform.core.config.settings.GROOMING_MVP_ENABLED", True)

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
    monkeypatch.setattr("app.platform.core.config.settings.GROOMING_MVP_ENABLED", True)

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
```

## 완료 기준 (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate

# 기존 테스트 + 신규 회귀 테스트 전체
pytest tests/test_recommend_api.py -v
# 모든 테스트 PASSED (기존 5개 + 신규 5개)
```

## 주의
- `monkeypatch.setattr`로 `settings.GROOMING_MVP_ENABLED`를 덮어쓸 때, `app.serving.api.recommend`에서 `settings`를 직접 참조하므로 `"app.platform.core.config.settings.GROOMING_MVP_ENABLED"`가 아닌 `"app.serving.api.recommend.settings.GROOMING_MVP_ENABLED"` 또는 `patch.object(settings, "GROOMING_MVP_ENABLED", True)` 방식 중 실제 동작하는 쪽을 선택한다.
