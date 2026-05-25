import hashlib
import json

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}

_GROOMING_WITH_LOCATION = json.dumps([
    {
        "name": "해피독미용",
        "mention_count": 5,
        "avg_freshness": 0.8,
        "score": 1.0,
        "road_address": "서울특별시 강남구 역삼동 123",
        "address": "서울 강남구 역삼동 123",
        "map_x": "1270276000",
        "map_y": "374979000",
        "telephone": "02-111-2222",
    }
], ensure_ascii=False)

_HOSPITAL_NO_LOCATION = json.dumps([
    {
        "name": "몽몽동물병원",
        "mention_count": 3,
        "avg_freshness": 0.7,
        "score": 0.9,
        # address 없음 → 제외되어야 함
    }
], ensure_ascii=False)


@pytest.fixture(autouse=True)
def patch_api_key(monkeypatch):
    monkeypatch.setattr("app.platform.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.platform.core.config.settings.ADMIN_API_KEY_HASH", "different_admin_hash")


def _make_redis_mock(data_by_key: dict):
    """key → raw JSON 문자열 매핑으로 Redis mock 생성."""
    mock = AsyncMock()
    mock.get = AsyncMock(side_effect=lambda key: data_by_key.get(key))
    return mock


@pytest.mark.asyncio
async def test_facilities_returns_items_with_location():
    mock_redis = _make_redis_mock({"popular:grooming": _GROOMING_WITH_LOCATION})

    with patch("app.serving.api.facilities.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/facilities", headers=HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_next"] is False
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["name"] == "해피독미용"
    assert item["category"] == "grooming"
    assert item["address"] == "서울특별시 강남구 역삼동 123"
    assert item["region_city"] == "서울"
    assert item["region_district"] == "강남구"
    assert item["phone"] == "02-111-2222"
    assert item["lat"] == pytest.approx(37.4979, abs=0.001)
    assert item["lng"] == pytest.approx(127.0276, abs=0.001)


@pytest.mark.asyncio
async def test_facilities_excludes_items_without_address():
    mock_redis = _make_redis_mock({
        "popular:grooming": _GROOMING_WITH_LOCATION,
        "popular:hospital": _HOSPITAL_NO_LOCATION,
    })

    with patch("app.serving.api.facilities.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/facilities", headers=HEADERS)

    assert resp.status_code == 200
    items = resp.json()["items"]
    names = [i["name"] for i in items]
    assert "해피독미용" in names
    assert "몽몽동물병원" not in names


@pytest.mark.asyncio
async def test_facilities_empty_redis_returns_empty_not_503():
    mock_redis = _make_redis_mock({})

    with patch("app.serving.api.facilities.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/facilities", headers=HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["has_next"] is False


@pytest.mark.asyncio
async def test_facilities_cursor_paging():
    entries = [
        {
            "name": f"샵{i}",
            "mention_count": 1,
            "avg_freshness": 0.5,
            "score": 0.5,
            "road_address": f"서울특별시 강남구 {i}번길",
            "map_x": "1270276000",
            "map_y": "374979000",
        }
        for i in range(5)
    ]
    mock_redis = _make_redis_mock({"popular:grooming": json.dumps(entries, ensure_ascii=False)})

    with patch("app.serving.api.facilities.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp1 = await ac.get("/facilities?cursor=0&limit=3", headers=HEADERS)
            resp2 = await ac.get("/facilities?cursor=3&limit=3", headers=HEADERS)

    assert resp1.status_code == 200
    assert len(resp1.json()["items"]) == 3
    assert resp1.json()["has_next"] is True
    assert resp1.json()["next_cursor"] == 3

    assert resp2.status_code == 200
    assert len(resp2.json()["items"]) == 2
    assert resp2.json()["has_next"] is False
    assert resp2.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_facilities_deduplicates_same_name_address():
    entry = {
        "name": "해피독",
        "mention_count": 5,
        "avg_freshness": 0.8,
        "score": 1.0,
        "road_address": "서울특별시 강남구 역삼동 1",
        "map_x": "1270276000",
        "map_y": "374979000",
    }
    # grooming과 hospital 두 키 모두에 같은 name+address 항목
    mock_redis = _make_redis_mock({
        "popular:grooming": json.dumps([entry], ensure_ascii=False),
        "popular:hospital": json.dumps([entry], ensure_ascii=False),
    })

    with patch("app.serving.api.facilities.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/facilities", headers=HEADERS)

    items = resp.json()["items"]
    assert len([i for i in items if i["name"] == "해피독"]) == 1


@pytest.mark.asyncio
async def test_facilities_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/facilities")
    assert resp.status_code == 401
