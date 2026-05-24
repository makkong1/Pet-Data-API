import asyncio
import html
import logging

from app.ingestion.blog import _TOP_N, _is_valid_name, _parse_freshness
from app.ingestion.naver import search_naver_blog, search_naver_local

_log = logging.getLogger(__name__)

_DISCOVER_SEM_LIMIT = 2
_VERIFY_SEM_LIMIT = 3
_EPS = 1e-9

_DISCOVERY_HINTS: dict[str, list[str]] = {
    "boarding": ["강아지위탁", "반려견유치원"],
    "hotel":    ["펫호텔", "강아지호텔", "반려동물호텔"],
}

_VERIFY_HINT: dict[str, str] = {
    "boarding": "강아지위탁",
    "hotel":    "펫호텔",
}

_DISCOVERY_REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전",
    "수원", "고양", "성남", "제주", "청주", "전주",
    "천안", "창원", "춘천",
]

# Local API 결과 title에 붙는 업종 접미사
_LOCAL_TITLE_SUFFIXES = [
    "펫호텔", "강아지호텔", "반려동물호텔", "애견호텔",
    "강아지위탁", "반려견위탁", "강아지유치원", "반려견유치원",
    "위탁센터", "호텔링센터",
]


def _clean_local_title(raw: str) -> str:
    name = html.unescape(raw)
    for suf in _LOCAL_TITLE_SUFFIXES:
        name = name.replace(suf, "").strip()
    # suffix 제거 후 남는 trailing 특수문자 정리 (& , . 등)
    return name.rstrip("&,. ")


def _name_in_post(name: str, title: str, desc: str) -> bool:
    return name in (title + " " + desc)


async def discover_via_local(context: str) -> list[dict]:
    """지역 × 업종 힌트 조합으로 Naver Local 검색 → 상호명 + 위치 정보 목록."""
    hints = _DISCOVERY_HINTS.get(context, [])
    if not hints:
        return []

    queries = [f"{r} {h}" for r in _DISCOVERY_REGIONS for h in hints] + hints
    sem = asyncio.Semaphore(_DISCOVER_SEM_LIMIT)

    async def _search(q: str) -> list[dict]:
        async with sem:
            return await search_naver_local(q, display=5)

    batches = await asyncio.gather(*[_search(q) for q in queries], return_exceptions=True)

    seen: set[str] = set()
    results: list[dict] = []
    for batch in batches:
        if isinstance(batch, Exception):
            continue
        for item in batch:
            name = _clean_local_title(item["title"])
            if not name or not _is_valid_name(name) or name in seen:
                continue
            seen.add(name)
            results.append({
                "name":         name,
                "address":      item.get("address") or None,
                "road_address": item.get("road_address") or None,
                "map_x":        item.get("map_x") or None,
                "map_y":        item.get("map_y") or None,
                "telephone":    item.get("telephone") or None,
            })

    _log.info("local_discovery discover done context=%s queries=%d names=%d",
              context, len(queries), len(results))
    return results


async def verify_blog_mentions(discovered: list[dict], context: str) -> list[dict]:
    """각 상호명으로 블로그 검색 → title/desc 포함 매칭 수 + freshness 스코어."""
    hint = _VERIFY_HINT.get(context, "")
    sem = asyncio.Semaphore(_VERIFY_SEM_LIMIT)

    async def _check(entry: dict) -> dict:
        name = entry["name"]
        query = f"{name} {hint}" if hint else name
        async with sem:
            try:
                items = await search_naver_blog(query, display=20, sort="sim")
            except Exception as exc:
                _log.warning("local_discovery verify_failed name=%r err=%s", name, exc)
                items = []

        matched = [
            i for i in items
            if _name_in_post(name, i.get("title", ""), i.get("description", ""))
        ]
        count = len(matched)
        freshness_sum = sum(_parse_freshness(i.get("postdate")) for i in matched)
        return {**entry, "_count": count, "_freshness_sum": freshness_sum}

    checked = await asyncio.gather(*[_check(e) for e in discovered])

    valid = [e for e in checked if e["_count"] >= 1]
    if not valid:
        return []

    for e in valid:
        avg_f = e["_freshness_sum"] / e["_count"]
        e["_avg_freshness"] = round(avg_f, 4)
        e["_raw_score"] = e["_count"] * avg_f

    max_raw = max(e["_raw_score"] for e in valid)
    if max_raw < _EPS:
        return []

    scored = []
    for e in valid:
        if e["_raw_score"] <= _EPS:
            continue
        scored.append({
            "name":          e["name"],
            "mention_count": e["_count"],
            "avg_freshness": e["_avg_freshness"],
            "score":         round(e["_raw_score"] / max_raw, 4),
            "address":       e.get("address"),
            "road_address":  e.get("road_address"),
            "map_x":         e.get("map_x"),
            "map_y":         e.get("map_y"),
            "telephone":     e.get("telephone"),
        })

    return sorted(scored, key=lambda x: x["score"], reverse=True)[:_TOP_N]


async def collect_popular_local_discovery(context: str) -> list[dict]:
    """Local discovery → Blog verification 2단계 파이프라인 (boarding, hotel 전용)."""
    discovered = await discover_via_local(context)
    if not discovered:
        _log.warning("local_discovery no names found context=%s", context)
        return []

    results = await verify_blog_mentions(discovered, context)
    _log.info("local_discovery collect done context=%s discovered=%d verified=%d",
              context, len(discovered), len(results))
    return results
