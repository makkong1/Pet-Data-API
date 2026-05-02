# Step 3 — 그루밍 블로그 멘션 추출

## 목적
네이버 블로그 검색 API → 타이틀·스니펫에서 미용 상호명 후보 추출 → `mention_count` 집계.  
결과는 **요청 스코프 메모리**에만 유지 (DB 영구 저장 금지, §2.7).

## 배경
- SSOT: `docs/GROOMING-RECOMMEND-MVP.md` §2.1, §2.4, §2.5
- 기존 `app/ingestion/naver.py`의 `search_naver_blog()` 함수를 **재사용** (import).
- 기존 `app/ingestion/analyzer/morpheme.py`의 `extract_nouns()` 함수를 **재사용** (import).
- 이 파이프는 기존 트렌드 Redis 파이프(`collect_category_trends`)와 **별 트랙**이다. 트렌드 파이프 수정 금지.
- Naver 타임아웃은 `settings.NAVER_TIMEOUT_MS / 1000` — 단, `search_naver_blog()`의 timeout 파라미터에 전달.

## 생성할 파일: `app/ingestion/grooming_blog.py`

```python
import re
from datetime import datetime, timezone
from typing import Optional

from app.ingestion.naver import search_naver_blog
from app.ingestion.analyzer.morpheme import extract_nouns
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
])

_CANDIDATE_CAP = 20  # §2.2 후보 상한 (Kakao 단계 진입 전)
_FRESHNESS_WINDOW_DAYS = 180  # freshness_weight 적용 기간


def _extract_candidates_from_text(text: str) -> set[str]:
    """타이틀·스니펫 텍스트 → 상호명 후보 집합."""
    candidates: set[str] = set()

    # 룰 기반: 패턴 추출
    for m in _PATTERN_SUFFIX.finditer(text):
        name = m.group(1).strip()
        if len(name) >= 2 and name not in _BLOCKLIST:
            candidates.add(name)
    for m in _PATTERN_PREFIX.finditer(text):
        name = m.group(1).strip()
        if len(name) >= 2 and name not in _BLOCKLIST:
            candidates.add(name)

    # 형태소 기반: 고유명사(NNP) 추출
    nouns = extract_nouns(text)
    for noun in nouns:
        if len(noun) >= 2 and noun not in _BLOCKLIST:
            candidates.add(noun)

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
) -> tuple[dict[str, dict], list[str]]:
    """
    그루밍 블로그 검색 → 상호명 멘션 집계.

    Returns:
        mention_map: {candidate_name: {"count": int, "freshness": float}}
        candidate_names: mention_count 내림차순 상위 _CANDIDATE_CAP 개 이름 목록 (Kakao 단계 입력용)
    """
    if timeout_s is None:
        timeout_s = settings.NAVER_TIMEOUT_MS / 1000

    # {상호명: {"count": int, "freshness_sum": float, "post_ids": set}}
    aggregator: dict[str, dict] = {}

    for query in _GROOMING_QUERIES:
        items = await search_naver_blog(query, display=100)
        for item in items:
            text = (item.get("title", "") + " " + item.get("description", "")).strip()
            post_id = item.get("link", text[:50])  # 글 단위 중복 방지용 ID
            postdate = item.get("postdate")
            freshness = _parse_freshness(postdate)

            candidates = _extract_candidates_from_text(text)
            for name in candidates:
                if name not in aggregator:
                    aggregator[name] = {"count": 0, "freshness_sum": 0.0, "post_ids": set()}
                entry = aggregator[name]
                if post_id not in entry["post_ids"]:
                    # 글 단위 1표 (§2.4 A안)
                    entry["count"] += 1
                    entry["freshness_sum"] += freshness
                    entry["post_ids"].add(post_id)

    # 후보 상한 적용 — mention_count 내림차순 상위 _CANDIDATE_CAP
    sorted_names = sorted(aggregator, key=lambda n: aggregator[n]["count"], reverse=True)
    top_names = sorted_names[:_CANDIDATE_CAP]

    mention_map: dict[str, dict] = {}
    for name in top_names:
        entry = aggregator[name]
        count = entry["count"]
        freshness = round(entry["freshness_sum"] / count, 4) if count > 0 else 0.0
        mention_map[name] = {"count": count, "freshness": freshness}

    return mention_map, top_names
```

## 생성할 파일: `tests/test_grooming_blog.py`

```python
import pytest
from unittest.mock import AsyncMock, patch

from app.ingestion.grooming_blog import (
    _extract_candidates_from_text,
    _parse_freshness,
    extract_grooming_mentions,
)


def test_extract_candidates_suffix_pattern():
    text = "해피독 미용실에서 스포팅컷을 받았어요"
    result = _extract_candidates_from_text(text)
    assert "해피독" in result


def test_extract_candidates_prefix_pattern():
    text = "애견 뽀삐샵 방문 후기"
    result = _extract_candidates_from_text(text)
    assert "뽀삐샵" in result


def test_extract_candidates_blocklist_excluded():
    text = "미용실 추천 애견 동물 샵"
    result = _extract_candidates_from_text(text)
    # 블록리스트 단어만 있으면 후보 없어야 함
    for name in result:
        assert len(name) >= 2


def test_parse_freshness_recent():
    from datetime import datetime, timezone, timedelta
    recent = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y%m%d")
    w = _parse_freshness(recent)
    assert 0.9 < w <= 1.0


def test_parse_freshness_old():
    w = _parse_freshness("20200101")
    assert w == 0.0


def test_parse_freshness_none():
    assert _parse_freshness(None) == 0.0


def test_parse_freshness_invalid():
    assert _parse_freshness("notadate") == 0.0


@pytest.mark.asyncio
async def test_extract_grooming_mentions_returns_capped():
    """블로그 결과에서 상위 20개 후보만 반환."""
    # 21개 이상의 고유 후보를 만들기 위해 충분한 다양한 제목을 만든다
    many_items = []
    for i in range(25):
        many_items.append({
            "title": f"미용실{i:02d} 미용실 후기",
            "description": "",
            "postdate": "20250101",
            "link": f"http://blog/{i}",
        })

    with patch("app.ingestion.grooming_blog.search_naver_blog", new=AsyncMock(return_value=many_items)):
        mention_map, candidate_names = await extract_grooming_mentions()

    assert len(candidate_names) <= 20


@pytest.mark.asyncio
async def test_extract_grooming_mentions_dedup_per_post():
    """동일 글(link)에서 같은 상호가 여러 번 나와도 1표."""
    same_post = [
        {
            "title": "해피독 미용실 정말 해피독 미용실",
            "description": "해피독 미용실이 최고",
            "postdate": "20250101",
            "link": "http://blog/same",
        }
    ]
    with patch("app.ingestion.grooming_blog.search_naver_blog", new=AsyncMock(return_value=same_post)):
        mention_map, _ = await extract_grooming_mentions()

    if "해피독" in mention_map:
        assert mention_map["해피독"]["count"] == 1


@pytest.mark.asyncio
async def test_extract_grooming_mentions_naver_fail_raises():
    """네이버 실패 시 예외를 그대로 올린다 (핸들러에서 폴백 처리)."""
    with patch(
        "app.ingestion.grooming_blog.search_naver_blog",
        new=AsyncMock(side_effect=Exception("naver down")),
    ):
        with pytest.raises(Exception, match="naver down"):
            await extract_grooming_mentions()
```

## 완료 기준 (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate
pytest tests/test_grooming_blog.py -v
# 모든 테스트 PASSED
```

## 주의
- `search_naver_blog()`는 `timeout` 파라미터를 받지 않을 수 있다. 기존 함수 시그니처 확인 후, timeout 전달이 필요하면 `naver.py`의 `fetch_public_api` 호출부 `timeout` 인자를 활용한다.
- 이 모듈은 네이버 실패 시 예외를 전파한다. 폴백(mention_count=0)은 Step 6 핸들러에서 처리한다.
- `aggregator` 딕셔너리의 `post_ids`는 메모리 집합(`set`)으로, DB나 Redis에 저장하지 않는다.
