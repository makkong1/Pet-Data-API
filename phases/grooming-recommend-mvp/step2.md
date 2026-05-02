# Step 2 — Kakao Local 키워드 검색 클라이언트

## 목적
상호명 후보 문자열 → Kakao Local 키워드 검색 → 장소 좌표·주소 반환.  
Redis TTL 캐시, 세마포어 동시성 제한, 후보 상한을 모두 포함한다.

## 배경
- SSOT: `docs/GROOMING-RECOMMEND-MVP.md` §2.2, §2.2.1
- 기존 `app/ingestion/geocoder.py`는 주소→좌표 변환용(address.json). 이번 클라이언트는 **키워드→장소** 검색용(keyword.json)으로 **별도 파일**로 분리한다.
- 캐시는 기존 `app/platform/cache/redis.py`의 `get_redis()`를 재사용한다.
- HTTP 타임아웃은 `settings.KAKAO_TIMEOUT_MS / 1000` (초 단위 변환).
- `settings.KAKAO_REST_API_KEY`가 빈 문자열이면 Kakao 호출 없이 빈 리스트 반환.

## 캐시 키 스키마 (§2.2.1 — SSOT)

| 항목 | 값 |
|------|----|
| 키 | `kakao:place:{normalized_name}:{lat_grid}:{lng_grid}` |
| `normalized_name` | 공백·특수문자 제거, 소문자 변환 |
| `lat_grid` / `lng_grid` | `f"{round(coord * 100) / 100:.4f}"` |
| TTL | 600초 |
| 저장 필드 | `name`, `address`, `lat`, `lng`만 (원문 JSON 전체 금지) |

## 생성할 파일: `app/ingestion/kakao.py`

```python
import asyncio
import json
import re
from typing import Optional
import httpx

from app.platform.core.config import settings
from app.platform.cache.redis import get_redis

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
_KAKAO_PLACE_TTL = 600  # §2.2.1
_CANDIDATE_CAP = 20     # §2.2
_SEMAPHORE = asyncio.Semaphore(5)  # §2.2 동시성 제한


def _normalize_name(name: str) -> str:
    """캐시 키용 정규화: 공백·특수문자 제거, 소문자."""
    return re.sub(r"[^가-힣a-z0-9]", "", name.lower())


def _coord_grid(coord: float) -> str:
    """좌표 양자화 → 캐시 키용 고정 포맷 문자열. §2.2.1"""
    return f"{round(coord * 100) / 100:.4f}"


def _cache_key(name: str, lat: float, lng: float) -> str:
    return f"kakao:place:{_normalize_name(name)}:{_coord_grid(lat)}:{_coord_grid(lng)}"


async def _get_cached(key: str) -> Optional[list[dict]]:
    r = get_redis()
    raw = await r.get(key)
    if raw:
        return json.loads(raw)
    return None


async def _set_cached(key: str, places: list[dict]) -> None:
    r = get_redis()
    await r.setex(key, _KAKAO_PLACE_TTL, json.dumps(places, ensure_ascii=False))


async def _call_kakao(name: str, lat: float, lng: float) -> list[dict]:
    """Kakao 키워드 검색 — 세마포어 보호."""
    headers = {"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"}
    params = {
        "query": name,
        "x": str(lng),
        "y": str(lat),
        "radius": 20000,
        "size": 5,
        "sort": "distance",
    }
    timeout = settings.KAKAO_TIMEOUT_MS / 1000
    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(KAKAO_KEYWORD_URL, headers=headers, params=params)
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
    return [
        {
            "name": d.get("place_name", ""),
            "address": d.get("road_address_name") or d.get("address_name", ""),
            "lat": float(d["y"]),
            "lng": float(d["x"]),
        }
        for d in docs
        if d.get("y") and d.get("x")
    ]


async def search_kakao_places(
    candidate_names: list[str],
    user_lat: float,
    user_lng: float,
) -> dict[str, list[dict]]:
    """
    상호명 후보 목록 → {원본 이름: [Kakao 장소 후보]} 반환.
    - 후보 상한(_CANDIDATE_CAP) 적용 후 Kakao 호출.
    - 캐시 HIT 시 HTTP 호출 생략.
    - settings.KAKAO_REST_API_KEY 없으면 빈 dict 반환.
    """
    if not settings.KAKAO_REST_API_KEY:
        return {}

    # §2.2 후보 상한: 상위 _CANDIDATE_CAP 개만 처리
    names = candidate_names[:_CANDIDATE_CAP]
    result: dict[str, list[dict]] = {}

    async def _fetch_one(name: str) -> None:
        key = _cache_key(name, user_lat, user_lng)
        cached = await _get_cached(key)
        if cached is not None:
            result[name] = cached
            return
        try:
            places = await _call_kakao(name, user_lat, user_lng)
        except Exception:
            result[name] = []
            return
        await _set_cached(key, places)
        result[name] = places

    await asyncio.gather(*[_fetch_one(n) for n in names])
    return result
```

## 생성할 파일: `tests/test_kakao_client.py`

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
    assert "37.5700" in key or "37.57" in key  # grid snapped


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

    async def fake_fetch(name, lat, lng):
        called_names.append(name)
        return []

    with patch("app.ingestion.kakao.settings") as mock_settings, \
         patch("app.ingestion.kakao._get_cached", new=AsyncMock(return_value=None)), \
         patch("app.ingestion.kakao._set_cached", new=AsyncMock()), \
         patch("app.ingestion.kakao._call_kakao", new=AsyncMock(side_effect=fake_fetch)):
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
```

## 완료 기준 (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate
pytest tests/test_kakao_client.py -v
# 모든 테스트 PASSED
```

## 주의
- `_SEMAPHORE`는 모듈 레벨에 선언한다 (asyncio.Semaphore는 이벤트 루프에 묶이므로 테스트에서 loop가 다를 경우 `asyncio.Semaphore(5)`를 함수 내부로 옮겨야 할 수 있음 — pytest-asyncio 환경에 따라 조정).
- Kakao 원문 JSON 전체를 캐시 값에 저장하지 않는다. `name`, `address`, `lat`, `lng` 4개 필드만 직렬화.
