import asyncio
import json
import logging
import re
import time
from typing import Optional
import httpx

from app.platform.core.config import settings
from app.platform.cache.redis import get_redis

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
_KAKAO_PLACE_TTL = 600  # §2.2.1
_CANDIDATE_CAP = 20     # §2.2
_SEMAPHORE = asyncio.Semaphore(5)  # §2.2 동시성 제한

_CONTEXT_ALIASES = {
    "snack": "supplies",
    "food": "supplies",
    "clothes": "supplies",
}
_QUERY_SUFFIXES = {
    "grooming": "애견미용",
    "hospital": "동물병원",
    "supplies": "반려동물용품",
}
_COMMON_HINTS = ("애견", "반려", "펫", "애완", "강아지", "고양이")
_CONTEXT_HINTS = {
    "grooming": ("미용", "그루밍"),
    "hospital": ("병원", "동물", "진료"),
    "supplies": ("용품", "사료", "간식"),
}

_log = logging.getLogger(__name__)


def _normalize_context(context: str) -> str:
    return _CONTEXT_ALIASES.get(context, context)


def _normalize_name(name: str) -> str:
    """캐시 키용 정규화: 공백·특수문자 제거, 소문자."""
    return re.sub(r"[^가-힣a-z0-9]", "", name.lower())


def _coord_grid(coord: float) -> str:
    """좌표 양자화 → 캐시 키용 고정 포맷 문자열. §2.2.1"""
    return f"{round(coord * 100) / 100:.4f}"


def _cache_key(name: str, lat: float, lng: float, context: str = "grooming") -> str:
    normalized_context = _normalize_context(context)
    return (
        f"kakao:place:{normalized_context}:"
        f"{_normalize_name(name)}:{_coord_grid(lat)}:{_coord_grid(lng)}"
    )


async def _get_cached(key: str) -> Optional[list[dict]]:
    r = get_redis()
    raw = await r.get(key)
    if raw:
        return json.loads(raw)
    return None


async def _set_cached(key: str, places: list[dict]) -> None:
    r = get_redis()
    await r.setex(key, _KAKAO_PLACE_TTL, json.dumps(places, ensure_ascii=False))


def _build_query(name: str, context: str = "grooming") -> str:
    normalized_context = _normalize_context(context)
    suffix = _QUERY_SUFFIXES.get(normalized_context, _QUERY_SUFFIXES["grooming"])
    return f"{name} {suffix}".strip()


def _is_pet_related_doc(doc: dict, context: str = "grooming") -> bool:
    normalized_context = _normalize_context(context)
    hay = f"{doc.get('place_name', '')} {doc.get('category_name', '')}".lower()
    hints = _COMMON_HINTS + _CONTEXT_HINTS.get(normalized_context, ())
    return any(token in hay for token in hints)


async def _call_kakao(name: str, lat: float, lng: float, context: str = "grooming") -> list[dict]:
    """Kakao 키워드 검색 — 세마포어 보호."""
    headers = {"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"}
    params = {
        "query": _build_query(name, context=context),
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
    docs = [d for d in docs if _is_pet_related_doc(d, context=context)]
    return [
        {
            "name": d.get("place_name", ""),
            "address": d.get("road_address_name") or d.get("address_name", ""),
            "category_name": d.get("category_name", ""),
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
    context: str = "grooming",
    req_id: Optional[str] = None,
) -> dict[str, list[dict]]:
    """
    상호명 후보 목록 → {원본 이름: [Kakao 장소 후보]} 반환.
    - 후보 상한(_CANDIDATE_CAP) 적용 후 Kakao 호출.
    - 캐시 HIT 시 HTTP 호출 생략.
    - settings.KAKAO_REST_API_KEY 없으면 빈 dict 반환.
    """
    rid = req_id or "-"
    t0 = time.monotonic()
    normalized_context = _normalize_context(context)

    if not settings.KAKAO_REST_API_KEY:
        _log.warning("kakao_place [%s] skip empty KAKAO_REST_API_KEY", rid)
        return {}

    names = candidate_names[:_CANDIDATE_CAP]
    result: dict[str, list[dict]] = {}
    stats = {"cache_hit": 0, "cache_miss": 0, "http_ok": 0, "http_err": 0}

    async def _fetch_one(name: str) -> None:
        key = _cache_key(name, user_lat, user_lng, context=normalized_context)
        cached = await _get_cached(key)
        if cached is not None:
            result[name] = cached
            stats["cache_hit"] += 1
            return
        stats["cache_miss"] += 1
        try:
            places = await _call_kakao(name, user_lat, user_lng, context=normalized_context)
            stats["http_ok"] += 1
        except Exception:
            stats["http_err"] += 1
            result[name] = []
            return
        await _set_cached(key, places)
        result[name] = places

    _log.info(
        "kakao_place [%s] start context=%s candidates_in=%d after_cap=%d lat=%.4f lng=%.4f",
        rid,
        normalized_context,
        len(candidate_names),
        len(names),
        user_lat,
        user_lng,
    )

    await asyncio.gather(*[_fetch_one(n) for n in names])

    places_nonzero = sum(1 for v in result.values() if v)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    _log.info(
        "kakao_place [%s] done context=%s keys=%d nonempty=%d cache_hit=%d cache_miss=%d http_ok=%d http_err=%d elapsed_ms=%d",
        rid,
        normalized_context,
        len(result),
        places_nonzero,
        stats["cache_hit"],
        stats["cache_miss"],
        stats["http_ok"],
        stats["http_err"],
        elapsed_ms,
    )

    return result
