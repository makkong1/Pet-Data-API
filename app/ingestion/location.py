import asyncio
import logging
from typing import Optional

from app.ingestion.naver import search_naver_local

_log = logging.getLogger(__name__)

_SEM_LIMIT = 3  # 동시 로컬 검색 요청 수

# context → Naver 장소 검색 시 붙이는 업종 힌트
_CONTEXT_PLACE_HINT: dict[str, str] = {
    "grooming":    "애견미용",
    "hospital":    "동물병원",
    "supplies":    "반려동물용품",
    "pharmacy":    "동물약국",
    "cafe":        "애견카페",
    "pension":     "반려동물펜션",
    "restaurant":  "반려동물식당",
    "boarding":    "강아지위탁",
    "hotel":       "펫호텔",
}


async def _lookup_location(name: str, hint: str, sem: asyncio.Semaphore) -> Optional[dict]:
    """단일 상호명에 대해 Naver 로컬 검색 → 첫 번째 결과 반환."""
    query = f"{name} {hint}"
    async with sem:
        results = await search_naver_local(query, display=3)
    if not results:
        return None
    # 검색 결과 중 상호명이 포함된 항목 우선, 없으면 첫 번째
    for r in results:
        if name in r["title"]:
            return r
    return results[0]


async def enrich_with_location(entries: list[dict], context: str) -> list[dict]:
    """popular 결과 리스트에 Naver 로컬 검색 결과(주소·좌표)를 붙여 반환.

    위치 정보를 찾지 못한 항목은 location 필드를 None으로 유지해 그대로 포함.
    """
    hint = _CONTEXT_PLACE_HINT.get(context, context)
    sem = asyncio.Semaphore(_SEM_LIMIT)

    tasks = [_lookup_location(e["name"], hint, sem) for e in entries]
    locations = await asyncio.gather(*tasks, return_exceptions=True)

    enriched = []
    found = 0
    for entry, loc in zip(entries, locations):
        row = dict(entry)
        if isinstance(loc, dict):
            row["address"] = loc.get("address") or None
            row["road_address"] = loc.get("road_address") or None
            row["map_x"] = loc.get("map_x") or None
            row["map_y"] = loc.get("map_y") or None
            row["telephone"] = loc.get("telephone") or None
            if row["address"] or row["road_address"]:
                found += 1
        else:
            row["address"] = None
            row["road_address"] = None
            row["map_x"] = None
            row["map_y"] = None
            row["telephone"] = None
        enriched.append(row)

    _log.info("location enrich done context=%s total=%d found=%d", context, len(entries), found)
    return enriched
