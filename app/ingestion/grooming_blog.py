import re
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.ingestion.naver import search_naver_blog, CATEGORY_KEYWORDS
from app.platform.core.config import settings

# 컨텍스트 정규화: 상품형 카테고리는 용품점 탐색으로 통합
_CONTEXT_ALIASES = {
    "snack": "supplies",
    "food": "supplies",
    "clothes": "supplies",
}

# 컨텍스트별 블로그 쿼리: supplies는 상품형 키워드까지 합쳐 후보를 모은다.
_CONTEXT_QUERIES = {
    "grooming": ["강아지 미용실 후기", "반려동물 미용실 추천"],
    "hospital": ["동물병원 후기", "반려동물 병원 추천", "24시 동물병원 후기"],
    "supplies": [
        *CATEGORY_KEYWORDS.get("supplies", []),
        *CATEGORY_KEYWORDS.get("snack", []),
        *CATEGORY_KEYWORDS.get("food", []),
    ],
}

# 컨텍스트별 최소 키워드 힌트 (노이즈 텍스트 early skip)
_CONTEXT_HINTS = {
    "grooming": ("미용", "그루밍", "애견", "반려"),
    "hospital": ("병원", "동물병원", "애견", "반려", "진료"),
    "supplies": ("용품", "펫샵", "사료", "간식", "애견", "반려", "펫"),
}

# 상호명 추출 규칙 패턴
_SUFFIX_PATTERNS = {
    "grooming": re.compile(r"(.{2,10})\s*(?:미용실|애견미용|펫미용|그루밍샵)"),
    "hospital": re.compile(r"(.{2,12})\s*(?:동물병원|24시동물병원|애견병원)"),
    "supplies": re.compile(r"(.{2,12})\s*(?:펫샵|용품점|애견용품점|반려동물용품점|펫스토어)"),
}
_PREFIX_PATTERNS = {
    "grooming": re.compile(r"(?:애견|반려견|펫)\s*(.{2,8})"),
    "hospital": re.compile(r"(?:동물병원|애견병원)\s*(.{2,8})"),
    "supplies": re.compile(r"(?:펫샵|용품점)\s*(.{2,8})"),
}

# 상호명 후보에서 제외할 일반 단어 블록리스트
_BLOCKLIST = frozenset([
    "미용실", "애견", "펫", "동물", "미용", "샵", "가게", "살롱", "병원",
    "용품", "용품점", "사료", "간식", "진료", "24시",
    "salon", "shop", "추천", "후기", "강아지", "고양이", "반려견",
    "강남", "서울", "부산", "근처", "인근", "주변", "동네",
    "자격증", "관리", "가위", "위생", "셀프", "전문", "학원",
])

_CANDIDATE_CAP = 20  # §2.2 후보 상한 (Kakao 단계 진입 전)
_FRESHNESS_WINDOW_DAYS = 180  # freshness_weight 적용 기간
_MIN_MENTION_COUNT = 2  # 노이즈 제거: 최소 글수 기준
_CANDIDATE_SANITIZE = re.compile(r"[\"'“”‘’·\[\]\(\)\{\}]")

_log = logging.getLogger(__name__)


def _normalize_context(context: str) -> str:
    return _CONTEXT_ALIASES.get(context, context)


def _extract_candidates_from_text(text: str, context: str = "grooming") -> set[str]:
    """타이틀·스니펫 텍스트 → 상호명 후보 집합."""
    candidates: set[str] = set()
    normalized_context = _normalize_context(context)
    hints = _CONTEXT_HINTS.get(normalized_context, ())
    lowered = text.lower()
    if hints and not any(h in lowered for h in hints):
        return candidates

    suffix_pattern = _SUFFIX_PATTERNS.get(normalized_context)
    prefix_pattern = _PREFIX_PATTERNS.get(normalized_context)

    def _clean(raw: str) -> str:
        return _CANDIDATE_SANITIZE.sub("", raw).strip()

    if suffix_pattern:
        for m in suffix_pattern.finditer(text):
            name = _clean(m.group(1))
            if len(name) >= 2 and name not in _BLOCKLIST:
                candidates.add(name)
    if prefix_pattern:
        for m in prefix_pattern.finditer(text):
            name = _clean(m.group(1))
            if len(name) >= 2 and name not in _BLOCKLIST:
                candidates.add(name)

    return candidates


def _parse_freshness(postdate: Optional[str]) -> float:
    """
    postdate(YYYYMMDD 또는 ISO)가 _FRESHNESS_WINDOW_DAYS 이내면 선형 가중치 반환.
    파싱 실패·없음 → 0.0. §2.5
    """
    if not postdate:
        return 0.0
    try:
        if len(postdate) == 8:  # YYYYMMDD
            dt = datetime.strptime(postdate, "%Y%m%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(postdate)
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days < 0 or age_days > _FRESHNESS_WINDOW_DAYS:
            return 0.0
        return round(1.0 - age_days / _FRESHNESS_WINDOW_DAYS, 4)
    except Exception:
        return 0.0


async def extract_context_mentions(
    context: str,
    timeout_s: Optional[float] = None,
    req_id: Optional[str] = None,
) -> tuple[dict[str, dict], list[str]]:
    """
    컨텍스트별 블로그 검색 → 상호명 멘션 집계.

    Returns:
        mention_map: {candidate_name: {"count": int, "freshness": float}}
        candidate_names: mention_count 내림차순 상위 _CANDIDATE_CAP 개 이름 목록 (Kakao 단계 입력용)
    """
    normalized_context = _normalize_context(context)
    queries = _CONTEXT_QUERIES.get(normalized_context, [])

    if timeout_s is None:
        timeout_s = settings.NAVER_TIMEOUT_MS / 1000

    rid = req_id or "-"
    t0 = time.monotonic()
    _log.info(
        "context_blog [%s] start context=%s normalized=%s queries=%d cap=%d timeout_s=%s",
        rid,
        context,
        normalized_context,
        len(queries),
        _CANDIDATE_CAP,
        timeout_s,
    )

    aggregator: dict[str, dict] = {}
    blog_item_total = 0

    for query in queries:
        items = await search_naver_blog(query, display=100)
        blog_item_total += len(items)
        for item in items:
            text = (item.get("title", "") + " " + item.get("description", "")).strip()
            post_id = item.get("link", text[:50])
            postdate = item.get("postdate")
            freshness = _parse_freshness(postdate)

            candidates = _extract_candidates_from_text(text, context=normalized_context)
            for name in candidates:
                if name not in aggregator:
                    aggregator[name] = {"count": 0, "freshness_sum": 0.0, "post_ids": set()}
                entry = aggregator[name]
                if post_id not in entry["post_ids"]:
                    entry["count"] += 1
                    entry["freshness_sum"] += freshness
                    entry["post_ids"].add(post_id)

    sorted_names = sorted(
        (
            name
            for name, entry in aggregator.items()
            if entry["count"] >= _MIN_MENTION_COUNT
        ),
        key=lambda n: aggregator[n]["count"],
        reverse=True,
    )
    top_names = sorted_names[:_CANDIDATE_CAP]

    mention_map: dict[str, dict] = {}
    for name in top_names:
        entry = aggregator[name]
        count = entry["count"]
        freshness = round(entry["freshness_sum"] / count, 4) if count > 0 else 0.0
        mention_map[name] = {"count": count, "freshness": freshness}

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    _log.info(
        "context_blog [%s] done context=%s normalized=%s blog_items=%d unique_before_cap=%d mention_map=%d top_names=%d elapsed_ms=%d",
        rid,
        context,
        normalized_context,
        blog_item_total,
        len(aggregator),
        len(mention_map),
        len(top_names),
        elapsed_ms,
    )
    if top_names:
        _log.info("context_blog [%s] top_names_sample=%s", rid, top_names[:10])

    return mention_map, top_names


async def extract_grooming_mentions(
    timeout_s: Optional[float] = None,
    req_id: Optional[str] = None,
) -> tuple[dict[str, dict], list[str]]:
    """하위 호환용 그루밍 전용 래퍼."""
    return await extract_context_mentions("grooming", timeout_s=timeout_s, req_id=req_id)
