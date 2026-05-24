import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from app.ingestion.naver import CATEGORY_KEYWORDS, search_naver_blog, search_naver_cafe
from app.platform.cache.redis import get_redis

_log = logging.getLogger(__name__)

# ── 점수 상수 ──────────────────────────────────────────────────────────
_FRESHNESS_WINDOW_DAYS = 180
_MIN_MENTION_COUNT = 2
_TOP_N = 20
_EPS = 1e-9

# ── Redis 키 ───────────────────────────────────────────────────────────
POPULAR_TTL = 25 * 3600  # 25h (배치 24h + 여유 1h)

# ── Context 설정 ───────────────────────────────────────────────────────
_CONTEXT_ALIASES: dict = {
    "snack": "supplies",
    "food": "supplies",
    "clothes": "supplies",
}

_CONTEXT_QUERIES: dict = {
    "grooming":    CATEGORY_KEYWORDS["grooming"],
    "hospital":    CATEGORY_KEYWORDS["hospital"],
    "supplies":    [
        *CATEGORY_KEYWORDS["supplies"],
        *CATEGORY_KEYWORDS["snack"],
        *CATEGORY_KEYWORDS["food"],
        *CATEGORY_KEYWORDS["clothes"],
    ],
    "pharmacy":    CATEGORY_KEYWORDS["pharmacy"],
    "cafe":        CATEGORY_KEYWORDS["cafe"],
    "pension":     CATEGORY_KEYWORDS["pension"],
    "restaurant":  CATEGORY_KEYWORDS["restaurant"],
    "boarding":    CATEGORY_KEYWORDS["boarding"],
    "hotel":       CATEGORY_KEYWORDS["hotel"],
}

# ── 상호명 추출 패턴 ───────────────────────────────────────────────────
_CONTEXT_HINTS: dict = {
    "grooming":   ("미용", "그루밍", "애견", "반려"),
    "hospital":   ("병원", "동물병원", "애견", "반려", "진료"),
    "supplies":   ("용품", "펫샵", "사료", "간식", "애견", "반려", "펫"),
    "pharmacy":   ("약국", "동물약국", "반려동물약국", "반려", "애견"),
    "cafe":       ("카페", "애견카페", "반려동물카페", "강아지", "반려"),
    "pension":    ("펜션", "반려동물펜션", "애견펜션", "강아지"),
    "restaurant": ("식당", "레스토랑", "반려동물동반", "강아지동반", "애견동반"),
    "boarding":   ("위탁", "호텔링", "펫시터", "반려동물"),
    "hotel":      ("호텔", "펫호텔", "반려동물호텔", "강아지호텔"),
}

_SUFFIX_PATTERNS: dict = {
    "grooming":   re.compile(r"([가-힣a-zA-Z0-9]{2,10})(?:\s+(?:애견|반려견|펫))?\s*(?:미용실|애견미용|펫미용|그루밍샵)"),
    "hospital":   re.compile(r"([가-힣a-zA-Z0-9]{2,12})\s*(?:동물병원|24시동물병원|애견병원)"),
    "supplies":   re.compile(r"([가-힣a-zA-Z0-9]{2,12})\s*(?:펫샵|용품점|애견용품점|반려동물용품점|펫스토어)"),
    "pharmacy":   re.compile(r"([가-힣a-zA-Z0-9]{2,10})\s*(?:동물약국|반려동물약국)"),
    "cafe":       re.compile(r"([가-힣a-zA-Z0-9]{2,10})\s*(?:애견카페|반려동물카페|펫카페)"),
    "pension":    re.compile(r"([가-힣a-zA-Z0-9]{2,10})\s*(?:반려동물펜션|애견펜션|펫펜션)"),
    "restaurant": re.compile(r"([가-힣a-zA-Z0-9]{2,12})\s*(?:반려동물동반식당|애견동반식당|펫프렌들리식당)"),
    "boarding":   re.compile(r"([가-힣a-zA-Z0-9]{2,12})\s*(?:위탁관리|호텔링센터|펫시터)"),
    "hotel":      re.compile(r"([가-힣a-zA-Z0-9]{2,10})\s*(?:펫호텔|반려동물호텔|애견호텔)"),
}

_PREFIX_PATTERNS: dict = {
    # 한국어 상호명은 <상호명>+<업종> suffix 형식이 지배적.
    # prefix 패턴(업종 키워드 뒤 캡처)은 업종 키워드 뒤에 오는
    # 아무 단어(약품명·조사·직책)를 잡아내므로 노이즈가 많음.
    # → hospital, pharmacy, boarding은 suffix 패턴만 사용.
    "grooming":   re.compile(r"(?:애견|반려견|펫)\s*([가-힣a-zA-Z0-9]{2,8})\s*(?:미용실|애견미용|펫미용|그루밍샵)"),
    "supplies":   re.compile(r"(?:펫샵|용품점)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "cafe":       re.compile(r"(?:애견카페|반려동물카페)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "pension":    re.compile(r"(?:반려동물펜션|애견펜션)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "restaurant": re.compile(r"(?:반려동물동반|애견동반)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "hotel":      re.compile(r"(?:펫호텔|반려동물호텔)\s*([가-힣a-zA-Z0-9]{2,8})"),
}

_BLOCKLIST_EXACT = frozenset([
    # 동물·업종 일반명사
    "강아지", "고양이", "반려동물", "반려견", "반려", "애견", "펫", "동물",
    "미용실", "미용", "샵", "살롱", "병원", "용품", "용품점",
    "사료", "간식", "진료", "24시", "24시간", "예약제",
    "동반", "가능", "편안", "청결", "전문",
    # 대명사·부사
    "저희", "우리", "함께", "같이", "바로", "항상", "여러",
    # 업종·상황 설명어 (상호명이 아닌 수식어)
    "일반", "심야", "야간", "실내", "대형", "신상", "근교", "야외",
    "서비스", "가격", "이용", "예약", "접종", "신종", "독채",
    "연중무휴", "가까운",
    # 동작·관계 명사
    "다녀온", "단골", "구매", "방문", "창업", "여행", "정보", "찾기",
    # 조사·어미
    "이나", "까지",
    # 음식점·숙박 카테고리 키워드
    "식당", "레스토랑", "맛집", "카페", "호텔", "리조트",
    # 서비스 유형 명사
    "펫시터", "프리미엄",
    # 약품명 (pharmacy prefix 패턴이 캡처)
    "심장사상충약",
    # 형용사형·상태어
    "다른", "만족스러운", "오픈형", "사실",
    # 반려동물 일반명사
    "애완동물",
    # 인사말·직책
    "안녕하세요", "코디네이터",
    # 동사형
    "다니던",
    # 약품명
    "넥스가드", "스펙트라", "심피드독",
])

_BLOCKLIST_CONTAINS = frozenset([
    "추천", "후기", "근처", "인근", "주변", "동네",
    "자격증", "학원", "협찬", "원고료", "광고", "반려동물",
    "근교",   # 서울근교 등
    "공항",   # 인천공항 등
    "유치원", # 애견유치원 등
    "분양",   # 강아지분양 등
    "동반",   # 애견동반 등 — 업종 수식어로만 쓰임
    "미용실", # 강아지미용실 등 — 캡처 그룹 내 업종명 중복
    "식당",   # 가능식당 등
    "카페",   # 힐링카페 등 — 업종명이 캡처 그룹에 포함된 경우
    "강아지", "고양이",  # 지명+동물 복합어 차단 (화원강아지, 강남강아지 등)
    "야간",   # 지명+야간 복합어 (안산야간애견 등)
    "24시",   # 지명+24시 복합어 (청주24시, 부산24시 등)
    "2차", "3차",  # 지명+지점번호 (부산2차 등)
    "전문",   # 안과전문 등 업종 수식어
    "약국",   # 광주약국 등 지명+업종명
    "할인",   # 할인카드 등
    "동구", "서구", "남구", "북구", "중구",  # 행정구역명 복합어 (울산동구애견 등)
    "반려",   # 지명+반려 복합어 (창원반려 등); _BLOCKLIST_EXACT의 substring 확장
])

_LOCATION_CITY = frozenset([
    # 특별·광역시
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    # 경기
    "수원", "성남", "고양", "용인", "부천", "안산", "안양", "남양주",
    "화성", "평택", "시흥", "파주", "의정부", "김포", "광명", "하남",
    "강남", "강북", "강서", "강동", "종로", "마포", "영등포", "노원",
    "분당", "일산", "판교", "화원",
    "동탄", "위례", "신논현", "양주",  # 경기 신도시·지구
    # 강원
    "춘천", "원주", "강릉", "속초", "양평", "가평", "연천", "홍천",
    # 충청
    "청주", "천안", "충주", "아산", "공주", "태안",
    # 전라
    "전주", "순천", "여수", "목포", "익산", "군산",
    # 경상
    "경주", "포항", "구미", "창원", "진주", "김해", "양산", "경산",
    "해운대", "광안리",  # 부산
    # 기타 지명·산 등
    "부평", "팔공산", "성산", "대구경산", "오산", "남악",
    # 제주
    "제주",
])

# 조사·어미 마지막 글자 필터
_GRAMMAR_ENDING = re.compile(r"(?:한|는|된|인|을|를|이|가|도|만|서|로|와|과|며|고|어|아|해|게|에|의|은|다|던)$")
_LOCATION_SUFFIX = re.compile(r"[가-힣]{1,5}(?:구|시|군|동|읍|면|로|역)$")
_HANGUL_MIN2 = re.compile(r"[가-힣]{2,}")
_CANDIDATE_SANITIZE = re.compile(u'[\\u0022\\u0027\\u201c\\u201d\\u2018\\u2019\\u00b7\\[\\]\\(\\)\\{\\}#@]')


def _is_valid_name(name: str) -> bool:
    if name in _BLOCKLIST_EXACT or name in _LOCATION_CITY:
        return False
    if any(b in name for b in _BLOCKLIST_CONTAINS):
        return False
    if _LOCATION_SUFFIX.search(name) or _GRAMMAR_ENDING.search(name):
        return False
    return bool(_HANGUL_MIN2.search(name))


def _normalize_context(context: str) -> str:
    return _CONTEXT_ALIASES.get(context, context)


def _extract_candidates_from_text(text: str, context: str) -> set:
    candidates: set = set()
    hints = _CONTEXT_HINTS.get(context, ())
    if hints and not any(h in text for h in hints):
        return candidates
    for pattern in (_SUFFIX_PATTERNS.get(context), _PREFIX_PATTERNS.get(context)):
        if pattern:
            for m in pattern.finditer(text):
                name = _CANDIDATE_SANITIZE.sub("", m.group(1)).strip()
                if _is_valid_name(name):
                    candidates.add(name)
    return candidates


# ── 점수 함수 ──────────────────────────────────────────────────────────

def _parse_freshness(postdate: Optional[str]) -> float:
    if not postdate:
        return 0.0
    try:
        if len(postdate) == 8:
            dt = datetime.strptime(postdate, "%Y%m%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(postdate)
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days < 0 or age_days > _FRESHNESS_WINDOW_DAYS:
            return 0.0
        return round(1.0 - age_days / _FRESHNESS_WINDOW_DAYS, 4)
    except Exception:
        return 0.0


def _compute_scores(aggregator: dict) -> list:
    """aggregator: {name: {"count": int, "freshness_sum": float}}"""
    entries = [
        (name, info)
        for name, info in aggregator.items()
        if info["count"] >= _MIN_MENTION_COUNT
    ]
    if not entries:
        return []

    scored = []
    for name, info in entries:
        count = info["count"]
        avg_freshness = round(info["freshness_sum"] / count, 4)
        scored.append({"name": name, "count": count, "avg_freshness": avg_freshness,
                       "raw_score": count * avg_freshness})

    max_raw = max(e["raw_score"] for e in scored)
    if max_raw < _EPS:
        return []

    return sorted(
        [{"name": e["name"], "mention_count": e["count"], "avg_freshness": e["avg_freshness"],
          "score": round(e["raw_score"] / max_raw, 4)}
         for e in scored if e["raw_score"] > _EPS],  # freshness=0인 stale 항목 제외
        key=lambda x: x["score"],
        reverse=True,
    )[:_TOP_N]


# ── 인기 수집 ──────────────────────────────────────────────────────────

async def extract_popular_names(context: str) -> list:
    """context별 Naver 블로그 검색 → 상호명 집계 → 점수 정규화."""
    normalized = _normalize_context(context)
    queries = _CONTEXT_QUERIES.get(normalized, [])
    if not queries:
        return []

    all_items: list = []
    for query in queries:
        for search_fn in (search_naver_blog, search_naver_cafe):
            try:
                items = await search_fn(query, display=100, sort="sim")
                all_items.extend(items)
            except Exception as exc:
                _log.warning(
                    "blog extract failed context=%s query=%r source=%s err=%s",
                    normalized, query, search_fn.__name__, exc,
                )

    # 전역 link dedupe
    seen_links: set = set()
    unique_items: list = []
    for item in all_items:
        link = item.get("link", "")
        if link and link not in seen_links:
            seen_links.add(link)
            unique_items.append(item)

    aggregator: dict = {}
    for item in unique_items:
        text = (item.get("title", "") + " " + item.get("description", "")).strip()
        freshness = _parse_freshness(item.get("postdate"))
        for name in _extract_candidates_from_text(text, normalized):
            if name not in aggregator:
                aggregator[name] = {"count": 0, "freshness_sum": 0.0}
            aggregator[name]["count"] += 1
            aggregator[name]["freshness_sum"] += freshness

    _log.info("blog extract done context=%s unique_posts=%d candidates=%d",
              normalized, len(unique_items), len(aggregator))
    return _compute_scores(aggregator)


async def save_popular(context: str, results: list) -> None:
    if not results:
        return
    r = get_redis()
    key = f"popular:{_normalize_context(context)}"
    await r.setex(key, POPULAR_TTL, json.dumps(results, ensure_ascii=False))
    _log.info("popular saved context=%s count=%d ttl=%d", context, len(results), POPULAR_TTL)


async def collect_popular_for_context(context: str) -> list:
    normalized = _normalize_context(context)
    return await extract_popular_names(normalized)
