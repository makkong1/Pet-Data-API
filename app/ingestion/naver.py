import asyncio
import httpx
import logging
import re
from typing import Optional
from app.platform.core.config import settings

logger = logging.getLogger(__name__)

NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "supplies":    ["반려동물 용품점 추천", "펫샵 추천"],
    "snack":       ["강아지 간식 추천", "고양이 간식 추천"],
    "food":        ["강아지 사료 추천", "고양이 사료 추천"],
    "grooming":    ["강아지 미용실 후기", "반려동물 미용실", "반려동물 미용실 추천"],
    "hospital":    ["동물병원 후기", "반려동물 병원 추천"],
    "clothes":     ["강아지 옷 추천", "반려동물 의류"],
    "pharmacy":    ["동물약국 추천", "반려동물 약국 후기"],
    "cafe":        ["반려동물 카페 추천", "강아지 동반 카페 후기", "애견카페 추천"],
    "pension":     ["반려동물 펜션 추천", "강아지 동반 펜션 후기"],
    "restaurant":  ["반려동물 동반 식당 추천", "강아지 동반 식당 후기", "애견 동반 레스토랑"],
    "boarding":    ["강아지 위탁관리 후기", "반려동물 호텔링 추천"],
    "hotel":       ["반려동물 호텔 추천", "강아지 호텔 후기", "펫호텔 추천"],
}

_RETRY_DELAYS = [1, 2, 4]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


async def _fetch_naver(url: str, params: dict, headers: dict, timeout: int = 30) -> dict:
    last_error: Optional[Exception] = None
    for delay in [0] + _RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            last_error = e
    raise last_error


async def search_naver_blog(query: str, display: int = 100, sort: str = "sim") -> list[dict]:
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": sort}
    timeout = settings.NAVER_TIMEOUT_MS // 1000
    data = await _fetch_naver(NAVER_BLOG_URL, params=params, headers=headers, timeout=timeout)
    items = data.get("items", [])
    return [
        {
            "title": _strip_html(i.get("title", "")),
            "description": _strip_html(i.get("description", "")),
            "link": i.get("link", ""),
            "postdate": i.get("postdate", ""),
            "blogger_name": i.get("bloggername", ""),
            "blogger_link": i.get("bloggerlink", ""),
        }
        for i in items
    ]


_NAVER_SEM_LIMIT = 4


async def collect_category_trends(category: str) -> list[dict]:
    queries = CATEGORY_KEYWORDS.get(category, [])
    semaphore = asyncio.Semaphore(_NAVER_SEM_LIMIT)

    async def _fetch(q: str, sort: str) -> list[dict]:
        async with semaphore:
            return await search_naver_blog(q, sort=sort)

    tasks = [_fetch(q, sort) for q in queries for sort in ("sim", "date")]
    batches = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set[str] = set()
    results: list[dict] = []
    for batch in batches:
        if isinstance(batch, Exception):
            logger.warning("naver blog fetch failed [%s]: %s", category, batch)
            continue
        for item in batch:
            link = item.get("link", "")
            if link and link not in seen:
                seen.add(link)
                results.append(item)
    return results
