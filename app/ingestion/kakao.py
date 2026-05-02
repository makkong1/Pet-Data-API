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
