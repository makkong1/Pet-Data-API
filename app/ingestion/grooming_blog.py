import re
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.ingestion.naver import search_naver_blog
from app.platform.core.config import settings

# 그루밍 전용 블로그 쿼리 (기존 CATEGORY_KEYWORDS와 별도 유지)
_GROOMING_QUERIES = ["강아지 미용실 후기", "반려동물 미용실 추천"]

# 상호명 추출 규칙 패턴
_PATTERN_SUFFIX = re.compile(r"(.{2,10})\s*(?:미용실|애견미용|펫미용|그루밍샵)")
_PATTERN_PREFIX = re.compile(r"(?:애견|반려견|펫)\s*(.{2,8})")

# 상호명 후보에서 제외할 일반 단어 블록리스트
_BLOCKLIST = frozenset([
    "미용실", "애견", "펫", "동물", "미용", "샵", "가게", "살롱",
    "salon", "shop", "추천", "후기", "강아지", "고양이", "반려견",
    "강남", "서울", "부산", "근처", "인근", "주변", "동네",
    "자격증", "관리", "가위", "위생", "셀프", "전문", "학원",
])

_CANDIDATE_CAP = 20  # §2.2 후보 상한 (Kakao 단계 진입 전)
_FRESHNESS_WINDOW_DAYS = 180  # freshness_weight 적용 기간
_MIN_MENTION_COUNT = 2  # 노이즈 제거: 최소 글수 기준
_CANDIDATE_SANITIZE = re.compile(r"[\"'“”‘’·\[\]\(\)\{\}]")

_log = logging.getLogger(__name__)


def _extract_candidates_from_text(text: str) -> set[str]:
    """타이틀·스니펫 텍스트 → 상호명 후보 집합."""
    candidates: set[str] = set()
    lowered = text.lower()
    if "미용" not in lowered and "그루밍" not in lowered and "애견" not in lowered and "반려" not in lowered:
        return candidates

    def _clean(raw: str) -> str:
        return _CANDIDATE_SANITIZE.sub("", raw).strip()

    for m in _PATTERN_SUFFIX.finditer(text):
        name = _clean(m.group(1))
        if len(name) >= 2 and name not in _BLOCKLIST:
            candidates.add(name)
    for m in _PATTERN_PREFIX.finditer(text):
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


async def extract_grooming_mentions(
    timeout_s: Optional[float] = None,
    req_id: Optional[str] = None,
) -> tuple[dict[str, dict], list[str]]:
    """
    그루밍 블로그 검색 → 상호명 멘션 집계.

    Returns:
        mention_map: {candidate_name: {"count": int, "freshness": float}}
        candidate_names: mention_count 내림차순 상위 _CANDIDATE_CAP 개 이름 목록 (Kakao 단계 입력용)
    """
    if timeout_s is None:
        timeout_s = settings.NAVER_TIMEOUT_MS / 1000

    rid = req_id or "-"
    t0 = time.monotonic()
    _log.info(
        "grooming_blog [%s] start queries=%d cap=%d timeout_s=%s",
        rid,
        len(_GROOMING_QUERIES),
        _CANDIDATE_CAP,
        timeout_s,
    )

    aggregator: dict[str, dict] = {}
    blog_item_total = 0

    for query in _GROOMING_QUERIES:
        items = await search_naver_blog(query, display=100)
        blog_item_total += len(items)
        for item in items:
            text = (item.get("title", "") + " " + item.get("description", "")).strip()
            post_id = item.get("link", text[:50])
            postdate = item.get("postdate")
            freshness = _parse_freshness(postdate)

            candidates = _extract_candidates_from_text(text)
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
        "grooming_blog [%s] done blog_items=%d unique_before_cap=%d mention_map=%d top_names=%d elapsed_ms=%d",
        rid,
        blog_item_total,
        len(aggregator),
        len(mention_map),
        len(top_names),
        elapsed_ms,
    )
    if top_names:
        _log.info("grooming_blog [%s] top_names_sample=%s", rid, top_names[:10])

    return mention_map, top_names
