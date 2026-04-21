import re
from app.core.config import settings
from app.collector.client import fetch_public_api

NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "snack":    ["강아지 간식 추천", "고양이 간식 추천"],
    "food":     ["강아지 사료 추천", "고양이 사료 추천"],
    "grooming": ["강아지 미용실 후기", "반려동물 미용"],
    "hospital": ["동물병원 후기", "반려동물 병원 추천"],
    "clothes":  ["강아지 옷 추천", "반려동물 의류"],
}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


async def search_naver_blog(query: str, display: int = 100) -> list[dict]:
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": "sim"}
    data = await fetch_public_api(NAVER_BLOG_URL, params=params, headers=headers, timeout=10)
    items = data.get("items", [])
    return [
        {"title": _strip_html(i.get("title", "")), "description": _strip_html(i.get("description", ""))}
        for i in items
    ]


async def collect_category_trends(category: str) -> list[dict]:
    queries = CATEGORY_KEYWORDS.get(category, [])
    results = []
    for query in queries:
        results.extend(await search_naver_blog(query))
    return results
