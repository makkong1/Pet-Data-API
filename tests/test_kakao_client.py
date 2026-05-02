import pytest
from unittest.mock import AsyncMock, patch

from app.ingestion.kakao import (
    _normalize_name,
    _coord_grid,
    _cache_key,
    search_kakao_places,
)


def test_normalize_name():
    assert _normalize_name("해피 독 미용실!") == "해피독미용실"
    assert _normalize_name("Happy Dog") == "happydog"


def test_coord_grid():
    assert _coord_grid(37.1234567) == "37.1200"
    assert _coord_grid(126.9876) == "126.9900"


def test_cache_key_format():
    key = _cache_key("해피독", 37.5665, 126.978)
    assert key.startswith("kakao:place:")
    # 한글은 정규화 후에도 유지, 공백·특수문자만 제거
    assert "해피독" in key
    parts = key.split(":")
    assert len(parts) == 5


@pytest.mark.asyncio
async def test_search_returns_empty_without_api_key():
    with patch("app.ingestion.kakao.settings") as mock_settings:
        mock_settings.KAKAO_REST_API_KEY = ""
        result = await search_kakao_places(["해피독"], 37.5, 126.9)
    assert result == {}


@pytest.mark.asyncio
async def test_search_uses_cache_hit():
    cached_places = [{"name": "해피독", "address": "서울", "lat": 37.5, "lng": 126.9}]

    with patch("app.ingestion.kakao.settings") as mock_settings, \
         patch("app.ingestion.kakao._get_cached", new=AsyncMock(return_value=cached_places)), \
         patch("app.ingestion.kakao._set_cached", new=AsyncMock()) as mock_set, \
         patch("app.ingestion.kakao._call_kakao", new=AsyncMock()) as mock_call:
        mock_settings.KAKAO_REST_API_KEY = "dummy"
        result = await search_kakao_places(["해피독"], 37.5, 126.9)

    mock_call.assert_not_called()
    mock_set.assert_not_called()
    assert result["해피독"] == cached_places


@pytest.mark.asyncio
async def test_search_caps_at_20_candidates():
    names = [f"미용실{i}" for i in range(30)]
    called_names = []

    async def fake_call(name, lat, lng):
        called_names.append(name)
        return []

    with patch("app.ingestion.kakao.settings") as mock_settings, \
         patch("app.ingestion.kakao._get_cached", new=AsyncMock(return_value=None)), \
         patch("app.ingestion.kakao._set_cached", new=AsyncMock()), \
         patch("app.ingestion.kakao._call_kakao", new=AsyncMock(side_effect=fake_call)):
        mock_settings.KAKAO_REST_API_KEY = "dummy"
        mock_settings.KAKAO_TIMEOUT_MS = 8000
        result = await search_kakao_places(names, 37.5, 126.9)

    assert len(result) == 20


@pytest.mark.asyncio
async def test_search_graceful_on_kakao_error():
    with patch("app.ingestion.kakao.settings") as mock_settings, \
         patch("app.ingestion.kakao._get_cached", new=AsyncMock(return_value=None)), \
         patch("app.ingestion.kakao._set_cached", new=AsyncMock()), \
         patch("app.ingestion.kakao._call_kakao", new=AsyncMock(side_effect=Exception("timeout"))):
        mock_settings.KAKAO_REST_API_KEY = "dummy"
        mock_settings.KAKAO_TIMEOUT_MS = 8000
        result = await search_kakao_places(["해피독"], 37.5, 126.9)

    assert result["해피독"] == []
