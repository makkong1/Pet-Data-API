import asyncio
import httpx
import logging
import re
from app.platform.core.config import settings

_log = logging.getLogger(__name__)

NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"
NAVER_LOCAL_URL = "https://openapi.naver.com/v1/search/local.json"

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "supplies":    ["반려동물 용품점 추천", "펫샵 추천", "애견용품점 후기", "반려동물 용품 잘하는 곳"],
    "snack":       ["강아지 간식 추천", "고양이 간식 추천", "강아지 수제간식 후기"],
    "food":        ["강아지 사료 추천", "고양이 사료 추천", "강아지 사료 잘하는 곳"],
    "grooming":    ["강아지 미용실 후기", "반려동물 미용실", "반려동물 미용실 추천",
                    "애견미용 잘하는 곳", "강아지 그루밍 후기", "펫미용샵 추천"],
    "hospital":    ["동물병원 후기", "반려동물 병원 추천", "동물병원 잘하는 곳", "애견병원 추천"],
    "clothes":     ["강아지 옷 추천", "반려동물 의류", "강아지 옷 잘하는 곳"],
    "pharmacy":    ["동물약국 추천", "반려동물 약국 후기", "동물약국 잘하는 곳", "반려동물 약 처방"],
    "cafe":        ["반려동물 카페 추천", "강아지 동반 카페 후기", "애견카페 추천",
                    "강아지카페 잘하는 곳", "펫카페 후기"],
    "pension":     ["반려동물 펜션 추천", "강아지 동반 펜션 후기", "애견펜션 후기", "강아지 펜션 잘하는 곳"],
    "restaurant":  ["반려동물 동반 식당 추천", "강아지 동반 식당 후기", "애견 동반 레스토랑",
                    "강아지 동반 맛집", "반려동물 동반 맛집 후기"],
    "boarding":    ["강아지 위탁관리 후기", "반려동물 호텔링 추천",
                    "강아지 위탁 잘하는 곳", "반려견 호텔링 후기", "펫시터 추천"],
    "hotel":       ["반려동물 호텔 추천", "강아지 호텔 후기", "펫호텔 추천",
                    "강아지 호텔 잘하는 곳", "반려동물 호텔 후기"],
}

_RETRY_DELAYS = [1, 2, 4]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _preview_text(s: str, n: int = 160) -> str:
    t = str(s).replace("\n", " ").strip()
    return t[:n] + ("…" if len(t) > n else "")


def _http_err_hint(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        txt = ""
        try:
            txt = exc.response.text
        except Exception:
            txt = ""
        return f"http_status={exc.response.status_code} body_preview={_preview_text(txt)!r}"
    if isinstance(exc, httpx.TimeoutException):
        return f"timeout {exc!r}"
    if isinstance(exc, httpx.RequestError):
        return f"request_error {type(exc).__name__}: {exc!r}"
    return f"{type(exc).__name__}: {exc!r}"


async def _fetch_naver(url: str, params: dict, headers: dict, timeout: int = 30) -> dict:
    url_short = url.rsplit("/", maxsplit=1)[-1] if "/" in url else url

    max_attempts = 1 + len(_RETRY_DELAYS)
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                keys = tuple(sorted(k for k in data if isinstance(k, str)))[:12]
                _log.debug(
                    "naver_blog http_ok endpoint=%s query_preview=%r attempt=%s/%s resp_keys(sample)=%s",
                    url_short,
                    _preview_text(str(params.get("query", "")), 80),
                    attempt + 1,
                    max_attempts,
                    keys,
                )
                return data
        except Exception as e:
            if attempt < len(_RETRY_DELAYS):
                sleep_s = _RETRY_DELAYS[attempt]
                _log.warning(
                    "naver_blog http_retry endpoint=%s query_preview=%r attempt=%s/%s sleep_s=%s %s",
                    url_short,
                    _preview_text(str(params.get("query", "")), 80),
                    attempt + 1,
                    max_attempts,
                    sleep_s,
                    _http_err_hint(e),
                )
                await asyncio.sleep(sleep_s)
                continue
            _log.error(
                "naver_blog http_gave_up endpoint=%s query_preview=%r attempts=%s %s",
                url_short,
                _preview_text(str(params.get("query", "")), 80),
                max_attempts,
                _http_err_hint(e),
            )
            raise


async def search_naver_blog(query: str, display: int = 100, sort: str = "sim") -> list[dict]:
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": sort}
    timeout = settings.NAVER_TIMEOUT_MS // 1000
    cid = settings.NAVER_CLIENT_ID.strip()
    client_id_tail = cid[-6:] if len(cid) >= 6 else "***"

    data = await _fetch_naver(NAVER_BLOG_URL, params=params, headers=headers, timeout=timeout)
    items = data.get("items", [])
    api_total = data.get("total")
    api_start = data.get("start")
    _log.info(
        "naver_blog search_ok query_preview=%r display=%s sort=%s timeout_s=%s client_id_tail=%s api_total=%r "
        "items_in_page=%s start=%s",
        _preview_text(query, 100),
        display,
        sort,
        timeout,
        client_id_tail,
        api_total,
        len(items),
        api_start,
    )
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


async def search_naver_local(query: str, display: int = 3) -> list[dict]:
    """Naver 장소 검색 — 상호명·주소·좌표 반환."""
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display}
    timeout = settings.NAVER_TIMEOUT_MS // 1000
    try:
        data = await _fetch_naver(NAVER_LOCAL_URL, params=params, headers=headers, timeout=timeout)
        items = data.get("items", [])
        return [
            {
                "title": _strip_html(i.get("title", "")),
                "category": i.get("category", ""),
                "address": i.get("address", ""),
                "road_address": i.get("roadAddress", ""),
                "map_x": i.get("mapx", ""),
                "map_y": i.get("mapy", ""),
                "telephone": i.get("telephone", ""),
            }
            for i in items
        ]
    except Exception as exc:
        _log.warning("naver_local search_failed query=%r err=%s", query, exc)
        return []


_NAVER_SEM_LIMIT = 4


async def collect_category_trends(category: str) -> list[dict]:
    queries = CATEGORY_KEYWORDS.get(category, [])
    if not queries:
        _log.warning("naver collect_category_trends category=%s: no CATEGORY_KEYWORDS (empty queries)", category)
        return []

    semaphore = asyncio.Semaphore(_NAVER_SEM_LIMIT)

    async def _fetch(q: str, sort: str) -> list[dict]:
        async with semaphore:
            return await search_naver_blog(q, sort=sort)

    tasks = [_fetch(q, sort) for q in queries for sort in ("sim", "date")]
    _log.info(
        "naver collect_category_trends start category=%r queries=%d parallel_calls=%d (sim+date) sem_limit=%d",
        category,
        len(queries),
        len(tasks),
        _NAVER_SEM_LIMIT,
    )

    batches = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set[str] = set()
    results: list[dict] = []
    dup_skip = raw_rows = 0
    errs: list[str] = []
    for batch in batches:
        if isinstance(batch, Exception):
            errs.append(f"{type(batch).__name__}: {batch}")
            _log.warning(
                "naver collect_category_trends batch_failed category=%r %s",
                category,
                _http_err_hint(batch),
            )
            continue
        raw_rows += len(batch)
        for item in batch:
            link = item.get("link", "")
            if not link:
                continue
            if link in seen:
                dup_skip += 1
                continue
            seen.add(link)
            results.append(item)

    _log.info(
        "naver collect_category_trends done category=%r unique_posts=%d raw_rows_seen=%d duplicate_links_skip=%d "
        "parallel_ok=%d parallel_err=%d",
        category,
        len(results),
        raw_rows,
        dup_skip,
        len(tasks) - len(errs),
        len(errs),
    )
    if errs:
        _log.warning(
            "naver collect_category_trends category=%r error_samples(max3)=%s",
            category,
            errs[:3],
        )

    return results
