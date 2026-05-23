# Popularity Intelligence API — 재설계 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pet-data-api를 "Popularity Intelligence API"로 재설계 — PostgreSQL·Kakao·LLM·공공 DB를 제거하고, Naver 블로그 언급 집계로 생성한 `GET /popular/{context}` 엔드포인트만 제공한다.

**Architecture:** Naver Blog API → blog.py(상호명 추출·점수) → Redis(`popular:{context}`) → `GET /popular/{context}`. 트렌드 배치(`GET /trends/{category}`)는 기존 유지. PostgreSQL·Kakao·LLM 제거.

**Tech Stack:** FastAPI, Redis (aioredis), httpx, kiwipiepy (analyzer — 변경 없음), APScheduler, rapidfuzz (삭제됨), pydantic-settings

---

## 파일 맵

| 역할 | 경로 |
|------|------|
| 신규 | `app/ingestion/blog.py` |
| 신규 | `app/serving/api/popular.py` |
| 신규 | `app/platform/schemas/popular.py` |
| 신규 | `tests/test_score.py` |
| 신규 | `tests/test_blog.py` |
| 신규 | `tests/test_popular_api.py` |
| 수정 | `app/ingestion/naver.py` (client.py 인라인 통합) |
| 수정 | `app/ingestion/runner.py` (전면 재작성) |
| 수정 | `app/platform/scheduler/jobs.py` (popular job 추가) |
| 수정 | `app/serving/api/trends.py` (timeseries 제거) |
| 수정 | `app/serving/api/collect.py` (targets body 재작성) |
| 수정 | `app/main.py` (router 정리) |
| 수정 | `app/platform/core/config.py` (삭제 설정 제거) |
| 삭제 | 아래 Task 1 삭제 목록 참조 |

---

### Task 1: 대량 삭제

**Files:**
- Delete: `app/ingestion/kakao.py`, `app/ingestion/geocoder.py`, `app/ingestion/business.py`, `app/ingestion/hospital.py`, `app/ingestion/pharmacy.py`, `app/ingestion/trend_history.py`
- Delete: `app/serving/api/recommend.py`, `app/serving/api/facilities.py`, `app/serving/api/stats.py`, `app/serving/api/search.py`, `app/serving/api/events.py`
- Delete: `app/serving/recommender/` (디렉터리 전체)
- Delete: `app/platform/core/database.py`
- Delete: `app/platform/models/` (디렉터리 전체)
- Delete: `app/platform/schemas/facility.py`, `app/platform/schemas/recommend.py`, `app/platform/schemas/stats.py`, `app/platform/schemas/events.py`
- Delete: `migrations/` (디렉터리 전체)
- Delete: `tests/test_grooming_ranker.py`, `tests/test_kakao_client.py`, `tests/test_kakao_place_filter.py`, `tests/test_recommend_api.py`, `tests/test_facilities_api.py`, `tests/test_recommender.py`, `tests/test_grooming_blog_mvp.py`, `tests/test_ranker.py`, `tests/test_business_collector.py`, `tests/test_hospital_collector.py`, `tests/test_geocoder.py`, `tests/test_collect_api.py`, `tests/test_trend_history.py`, `tests/test_events_api.py`, `tests/test_search_api.py`, `tests/test_facility_models.py`

> `app/ingestion/client.py`와 `app/ingestion/grooming_blog.py`는 아직 삭제하지 않는다. 각각 Task 3, Task 6에서 교체 후 삭제.

- [ ] **Step 1: 소스 파일 삭제**

```bash
rm app/ingestion/kakao.py app/ingestion/geocoder.py \
   app/ingestion/business.py app/ingestion/hospital.py \
   app/ingestion/pharmacy.py app/ingestion/trend_history.py

rm app/serving/api/recommend.py app/serving/api/facilities.py \
   app/serving/api/stats.py app/serving/api/search.py \
   app/serving/api/events.py

rm -rf app/serving/recommender/
rm app/platform/core/database.py
rm -rf app/platform/models/
rm app/platform/schemas/facility.py app/platform/schemas/recommend.py \
   app/platform/schemas/stats.py app/platform/schemas/events.py
rm -rf migrations/
```

- [ ] **Step 2: 테스트 파일 삭제**

```bash
rm tests/test_grooming_ranker.py tests/test_kakao_client.py \
   tests/test_kakao_place_filter.py tests/test_recommend_api.py \
   tests/test_facilities_api.py tests/test_recommender.py \
   tests/test_grooming_blog_mvp.py tests/test_ranker.py \
   tests/test_business_collector.py tests/test_hospital_collector.py \
   tests/test_geocoder.py tests/test_collect_api.py \
   tests/test_trend_history.py tests/test_events_api.py \
   tests/test_search_api.py tests/test_facility_models.py
```

- [ ] **Step 3: platform __init__.py 정리 — 삭제된 모듈 import 제거**

`app/platform/models/__init__.py`를 삭제했으므로 `app/platform/schemas/__init__.py`에 모델 관련 import가 있으면 제거한다.

```bash
cat app/platform/schemas/__init__.py
```

빈 파일이거나 삭제된 모듈 import가 없으면 넘어간다. 있으면 해당 줄만 제거.

- [ ] **Step 4: 삭제 확인**

```bash
ls app/ingestion/ app/serving/api/ app/platform/schemas/ tests/
```

Expected — ingestion에 남은 것: `__init__.py`, `analyzer/`, `client.py`, `grooming_blog.py`, `naver.py`, `runner.py`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: 공공DB·Kakao·LLM·추천 관련 파일 일괄 삭제 — Popularity Intelligence 재설계"
```

---

### Task 2: 깨진 임포트 수정

**Files:**
- Modify: `app/main.py`
- Modify: `app/serving/api/trends.py`
- Modify: `app/platform/scheduler/jobs.py`
- Modify: `app/ingestion/runner.py`
- Modify: `app/serving/api/collect.py`

Task 1 이후 서버가 임포트 에러로 죽는다. 이 태스크가 끝나면 서버가 다시 기동되어야 한다.

- [ ] **Step 1: main.py — 삭제된 라우터 제거**

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.serving.api.collect import router as collect_router
from app.serving.api.trends import router as trends_router
from app.platform.scheduler.jobs import start_scheduler, stop_scheduler
from app.platform.observability import attach_observability


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Popularity Intelligence API (Pet Data API)",
    description=(
        "Naver 블로그 기반 반려동물 서비스 인기도 API "
        "(Popularity intelligence from blog mentions)"
    ),
    lifespan=lifespan,
)
attach_observability(app)
app.include_router(collect_router)
app.include_router(trends_router)
```

- [ ] **Step 2: trends.py — timeseries 엔드포인트 및 DB 임포트 제거**

```python
# app/serving/api/trends.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from redis.exceptions import RedisError
from app.platform.cache.redis import get_trend, get_updated_at
from app.platform.core.auth import require_api_key
from app.ingestion.naver import CATEGORY_KEYWORDS
from app.platform.observability import get_request_id

router = APIRouter(prefix="/trends", tags=["트렌드 (Trends)"])
_log = logging.getLogger(__name__)

VALID_CATEGORIES = set(CATEGORY_KEYWORDS.keys())


@router.get(
    "/{category}",
    summary="카테고리별 트렌드 (Trends by category)",
    description="Redis에 캐시된 키워드 순위. (Keyword rankings from Redis cache.)",
)
async def get_trends(
    request: Request,
    category: str = Path(..., description="트렌드 카테고리 (Registered trend category)"),
    limit: int = Query(20, ge=1, le=50, description="키워드 개수 상한 (Max keywords)"),
    _: None = Depends(require_api_key),
):
    rid = get_request_id(request)
    _log.info("[%s] get_trends category=%s limit=%d -> Redis 조회", rid, category, limit)
    if category not in VALID_CATEGORIES:
        _log.info("[%s] get_trends category=%s -> 404 unknown", rid, category)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown category: {category}")

    try:
        keywords = await get_trend(category, limit)
        updated_at = await get_updated_at(category)
    except RedisError:
        _log.warning("[%s] get_trends category=%s -> 503 Redis error", rid, category)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Cache unavailable")

    if not keywords:
        _log.warning("[%s] get_trends category=%s -> 503 empty", rid, category)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Trend data unavailable")
    _log.info("[%s] get_trends category=%s -> keywords=%d updated_at=%s", rid, category, len(keywords), updated_at)
    return {
        "category": category,
        "updated_at": updated_at,
        "keywords": [{"keyword": k, "score": int(s)} for k, s in keywords],
    }
```

- [ ] **Step 3: runner.py — DB 의존 제거, run_trend_collection만 남김**

```python
# app/ingestion/runner.py
from app.ingestion.naver import collect_category_trends, CATEGORY_KEYWORDS
from app.ingestion.analyzer.trend import aggregate_keywords
from app.platform.cache.redis import save_trend


async def run_trend_collection() -> list[dict]:
    results = []
    for category in CATEGORY_KEYWORDS:
        try:
            items = await collect_category_trends(category)
            counts = aggregate_keywords(items)
            await save_trend(category, dict(counts))
            results.append({"category": category, "status": "success", "keywords_count": len(counts)})
        except Exception as e:
            results.append({"category": category, "status": "failed", "error_message": str(e)})
    return results
```

> `run_popular_collection`은 Task 8에서 추가된다.

- [ ] **Step 4: jobs.py — DB 임포트 + scheduled_collection 제거**

```python
# app/platform/scheduler/jobs.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.ingestion.runner import run_trend_collection

scheduler = AsyncIOScheduler()


def start_scheduler():
    scheduler.add_job(
        run_trend_collection,
        trigger="cron",
        hour=18,
        minute=0,
        max_instances=1,
        id="daily_trend_collection",
    )
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
```

> popular job은 Task 8에서 추가된다.

- [ ] **Step 5: collect.py — AsyncSessionLocal 제거, 임시 stub**

```python
# app/serving/api/collect.py
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from app.platform.core.auth import require_admin_key
from app.platform.observability import get_request_id
from app.ingestion.runner import run_trend_collection

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/collect", tags=["관리자 (Admin)"])


async def _run_trends_background() -> None:
    try:
        result = await run_trend_collection()
        _log.info("background trend collection done result=%s", result)
    except Exception as e:
        _log.error("background trend collection failed error=%s", e)


@router.post(
    "/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="수집 실행 (Trigger collection)",
    response_model=dict,
)
async def trigger_collection(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin_key),
):
    rid = get_request_id(request)
    _log.info("[%s] trigger_collection -> trends background", rid)
    background_tasks.add_task(_run_trends_background)
    return {"message": "collection started", "targets": ["trends"]}
```

> Task 9에서 `targets` body param을 지원하도록 재작성한다.

- [ ] **Step 6: 서버 임포트 검증**

```bash
python -c "from app.main import app; print('OK')"
```

Expected: `OK` (에러 없음)

- [ ] **Step 7: 남은 테스트 실행**

```bash
pytest tests/test_analyzer.py tests/test_auth.py \
       tests/test_naver_collector.py tests/test_observability.py \
       tests/test_trends_api.py tests/test_grooming_blog.py -v
```

Expected: 모두 PASS (일부 스킵 허용, 실패 없어야 함)

- [ ] **Step 8: Commit**

```bash
git add app/main.py app/serving/api/trends.py app/platform/scheduler/jobs.py \
        app/ingestion/runner.py app/serving/api/collect.py
git commit -m "fix: 삭제된 모듈 임포트 제거 — 서버 기동 복구"
```

---

### Task 3: naver.py — client.py 인라인 통합 + 삭제

**Files:**
- Modify: `app/ingestion/naver.py`
- Delete: `app/ingestion/client.py`

`client.py`의 `fetch_public_api`(retry 로직)를 naver.py 내 private 함수 `_fetch_naver`로 인라인한다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_naver_collector.py 에 아래 테스트 추가
# (파일이 이미 있으므로 기존 파일 끝에 추가)
import pytest
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_search_naver_blog_retries_on_failure():
    """fetch 실패 시 최대 3회 재시도 후 예외 발생."""
    call_count = 0

    async def failing_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise Exception("network error")

    with patch("app.ingestion.naver.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = failing_get
        mock_client_cls.return_value = mock_client

        with patch("app.ingestion.naver.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(Exception, match="network error"):
                from app.ingestion.naver import search_naver_blog
                await search_naver_blog("테스트", sort="sim")

    assert call_count == 4  # 초기 1회 + 재시도 3회
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_naver_collector.py::test_search_naver_blog_retries_on_failure -v
```

Expected: FAIL — `_fetch_naver` 없음 / client.py 경로

- [ ] **Step 3: naver.py 수정 — _fetch_naver 인라인, client.py import 제거**

```python
# app/ingestion/naver.py
import asyncio
import httpx
import logging
import re
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
    last_error: Exception | None = None
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
```

- [ ] **Step 4: client.py 삭제**

```bash
rm app/ingestion/client.py
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/test_naver_collector.py -v
```

Expected: 모두 PASS

- [ ] **Step 6: Commit**

```bash
git add app/ingestion/naver.py tests/test_naver_collector.py
git commit -m "refactor(naver): fetch_public_api 인라인 → client.py 삭제"
```

---

### Task 4: config.py — 삭제된 설정 제거

**Files:**
- Modify: `app/platform/core/config.py`

- [ ] **Step 1: config.py 재작성**

```python
# app/platform/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_KEY_HASH: str
    ADMIN_API_KEY_HASH: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    REDIS_URL: str = "redis://localhost:6379/0"
    NAVER_TIMEOUT_MS: int = 10_000

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 2: 임포트 검증**

```bash
python -c "from app.platform.core.config import settings; print('OK')"
```

Expected: `OK` (.env에 NAVER_CLIENT_ID 등 필수값이 있어야 함; 없으면 `NAVER_CLIENT_ID=dummy NAVER_CLIENT_SECRET=dummy API_KEY_HASH=x ADMIN_API_KEY_HASH=x python -c "..."`)

- [ ] **Step 3: Commit**

```bash
git add app/platform/core/config.py
git commit -m "refactor(config): DATABASE_URL·KAKAO·OLLAMA·공공API 설정 제거"
```

---

### Task 5: blog.py — 점수 함수 TDD

**Files:**
- Create: `app/ingestion/blog.py` (점수 함수만, 나머지는 Task 6)
- Create: `tests/test_score.py`

`_parse_freshness`와 `_compute_scores`를 TDD로 구현한다. `_compute_scores`는 `max(raw_score) < 1e-9`일 때 빈 리스트를 반환한다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_score.py
import pytest
from datetime import datetime, timezone, timedelta
from app.ingestion.blog import _parse_freshness, _compute_scores


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y%m%d")


def test_parse_freshness_today():
    assert _parse_freshness(_days_ago(0)) == pytest.approx(1.0, abs=0.01)


def test_parse_freshness_90_days():
    assert _parse_freshness(_days_ago(90)) == pytest.approx(0.5, abs=0.02)


def test_parse_freshness_over_180_days():
    assert _parse_freshness(_days_ago(181)) == 0.0


def test_parse_freshness_none():
    assert _parse_freshness(None) == 0.0


def test_parse_freshness_invalid():
    assert _parse_freshness("invalid") == 0.0


def test_compute_scores_basic():
    aggregator = {
        "해피독": {"count": 5, "freshness_sum": 4.0},
        "멍멍샵": {"count": 3, "freshness_sum": 2.4},
    }
    result = _compute_scores(aggregator)
    assert len(result) == 2
    assert result[0]["name"] == "해피독"
    assert result[0]["score"] == pytest.approx(1.0)
    assert 0.0 < result[1]["score"] <= 1.0
    assert all(0.0 <= r["score"] <= 1.0 for r in result)


def test_compute_scores_min_mention_filter():
    aggregator = {
        "해피독": {"count": 5, "freshness_sum": 4.0},
        "노이즈": {"count": 1, "freshness_sum": 0.8},
    }
    result = _compute_scores(aggregator)
    names = [r["name"] for r in result]
    assert "해피독" in names
    assert "노이즈" not in names


def test_compute_scores_all_stale_returns_empty():
    # avg_freshness=0 → raw_score=0 → max<eps → []
    aggregator = {
        "해피독": {"count": 5, "freshness_sum": 0.0},
        "멍멍샵": {"count": 3, "freshness_sum": 0.0},
    }
    assert _compute_scores(aggregator) == []


def test_compute_scores_empty():
    assert _compute_scores({}) == []


def test_compute_scores_top20_limit():
    aggregator = {
        f"미용실{i}": {"count": i + 2, "freshness_sum": float(i + 2)}
        for i in range(30)
    }
    result = _compute_scores(aggregator)
    assert len(result) == 20


def test_compute_scores_result_fields():
    aggregator = {"해피독": {"count": 4, "freshness_sum": 3.2}}
    result = _compute_scores(aggregator)
    assert len(result) == 1
    r = result[0]
    assert r["name"] == "해피독"
    assert r["mention_count"] == 4
    assert r["avg_freshness"] == pytest.approx(0.8, abs=0.001)
    assert r["score"] == pytest.approx(1.0)
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_score.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.ingestion.blog'`

- [ ] **Step 3: blog.py — 점수 함수만 구현**

```python
# app/ingestion/blog.py
from datetime import datetime, timezone

_FRESHNESS_WINDOW_DAYS = 180
_MIN_MENTION_COUNT = 2
_TOP_N = 20
_EPS = 1e-9


def _parse_freshness(postdate: str | None) -> float:
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


def _compute_scores(aggregator: dict[str, dict]) -> list[dict]:
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
        raw_score = count * avg_freshness
        scored.append({"name": name, "count": count, "avg_freshness": avg_freshness, "raw_score": raw_score})

    max_raw = max(e["raw_score"] for e in scored)
    if max_raw < _EPS:
        return []

    result = sorted(
        [
            {
                "name": e["name"],
                "mention_count": e["count"],
                "avg_freshness": e["avg_freshness"],
                "score": round(e["raw_score"] / max_raw, 4),
            }
            for e in scored
        ],
        key=lambda x: x["score"],
        reverse=True,
    )[:_TOP_N]
    return result
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_score.py -v
```

Expected: 모두 PASS

- [ ] **Step 5: Commit**

```bash
git add app/ingestion/blog.py tests/test_score.py
git commit -m "feat(blog): _parse_freshness·_compute_scores TDD 구현"
```

---

### Task 6: blog.py — 완성 + test_blog.py + grooming_blog.py 삭제

**Files:**
- Modify: `app/ingestion/blog.py` (추출·집계·저장 함수 추가)
- Create: `tests/test_blog.py`
- Delete: `app/ingestion/grooming_blog.py`, `tests/test_grooming_blog.py`

`extract_popular_names`는 context별 쿼리를 모두 실행한 뒤 **link 기준 전역 dedupe** 후 상호명을 추출한다. `save_popular`는 결과가 비어 있으면 Redis를 갱신하지 않는다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_blog.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_extract_popular_names_cross_query_link_dedupe():
    """동일 link가 여러 쿼리에서 반환되어도 mention_count는 1."""
    dup_post = {
        "title": "해피독 미용실 후기",
        "description": "해피독미용실 방문기",
        "link": "https://blog.naver.com/unique",
        "postdate": "20260501",
    }

    async def fake_search(query, display=100, sort="sim"):
        return [dup_post]

    with patch("app.ingestion.blog.search_naver_blog", side_effect=fake_search):
        from app.ingestion.blog import extract_popular_names
        result = await extract_popular_names("grooming")

    해피독_entries = [r for r in result if r["name"] == "해피독"]
    if 해피독_entries:
        assert 해피독_entries[0]["mention_count"] == 1


@pytest.mark.asyncio
async def test_extract_popular_names_unknown_context_returns_empty():
    with patch("app.ingestion.blog.search_naver_blog", new=AsyncMock(return_value=[])):
        from app.ingestion.blog import extract_popular_names
        result = await extract_popular_names("unknown_xyz")
    assert result == []


@pytest.mark.asyncio
async def test_save_popular_skips_empty():
    with patch("app.ingestion.blog.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        from app.ingestion.blog import save_popular
        await save_popular("grooming", [])
    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_save_popular_writes_json():
    import json
    results = [{"name": "해피독", "mention_count": 5, "avg_freshness": 0.8, "score": 1.0}]
    with patch("app.ingestion.blog.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        from app.ingestion.blog import save_popular, POPULAR_TTL
        await save_popular("grooming", results)
    mock_redis.setex.assert_called_once()
    key, ttl, payload = mock_redis.setex.call_args.args
    assert key == "popular:grooming"
    assert ttl == POPULAR_TTL
    assert json.loads(payload) == results


@pytest.mark.asyncio
async def test_collect_popular_for_context_aliases_supplies():
    """snack → supplies로 정규화된 쿼리셋을 사용."""
    called_queries: list[str] = []

    async def fake_search(query, display=100, sort="sim"):
        called_queries.append(query)
        return []

    with patch("app.ingestion.blog.search_naver_blog", side_effect=fake_search):
        from app.ingestion.blog import collect_popular_for_context
        await collect_popular_for_context("snack")

    # snack → supplies 로 정규화 → supplies+snack+food+clothes 쿼리 8개
    assert len(called_queries) == 8
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_blog.py -v
```

Expected: `ImportError` — `extract_popular_names` / `save_popular` not found in blog.py

- [ ] **Step 3: blog.py 완성**

`app/ingestion/blog.py` 전체 내용 (Task 5 함수 포함):

```python
# app/ingestion/blog.py
import json
import logging
import re
from datetime import datetime, timezone

from app.ingestion.naver import CATEGORY_KEYWORDS, search_naver_blog
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
_CONTEXT_ALIASES: dict[str, str] = {
    "snack": "supplies",
    "food": "supplies",
    "clothes": "supplies",
}

_CONTEXT_QUERIES: dict[str, list[str]] = {
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
_CONTEXT_HINTS: dict[str, tuple[str, ...]] = {
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

_SUFFIX_PATTERNS: dict[str, re.Pattern] = {
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

_PREFIX_PATTERNS: dict[str, re.Pattern] = {
    "grooming":   re.compile(r"(?:애견|반려견|펫)\s*([가-힣a-zA-Z0-9]{2,8})\s*(?:미용실|애견미용|펫미용|그루밍샵)"),
    "hospital":   re.compile(r"(?:동물병원|애견병원)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "supplies":   re.compile(r"(?:펫샵|용품점)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "pharmacy":   re.compile(r"(?:동물약국|반려동물약국)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "cafe":       re.compile(r"(?:애견카페|반려동물카페)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "pension":    re.compile(r"(?:반려동물펜션|애견펜션)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "restaurant": re.compile(r"(?:반려동물동반|애견동반)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "boarding":   re.compile(r"(?:위탁관리|호텔링)\s*([가-힣a-zA-Z0-9]{2,8})"),
    "hotel":      re.compile(r"(?:펫호텔|반려동물호텔)\s*([가-힣a-zA-Z0-9]{2,8})"),
}

_BLOCKLIST_EXACT = frozenset([
    "강아지", "고양이", "반려동물", "반려견", "애견", "펫", "동물",
    "미용실", "미용", "샵", "살롱", "병원", "용품", "용품점",
    "사료", "간식", "진료", "24시", "예약제",
    "동반", "가능", "편안", "청결", "전문",
])

_BLOCKLIST_CONTAINS = frozenset([
    "추천", "후기", "근처", "인근", "주변", "동네",
    "자격증", "학원", "협찬", "원고료", "광고", "반려동물",
])

_LOCATION_CITY = frozenset([
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "수원", "성남", "고양", "용인", "부천", "안산", "안양", "남양주",
    "화성", "평택", "시흥", "파주", "의정부", "김포", "광명", "하남",
    "강남", "강북", "강서", "강동", "종로", "마포", "영등포", "노원",
    "분당", "일산", "판교", "화원", "제주",
])

_GRAMMAR_ENDING = re.compile(r"(?:한|는|된|인|을|를|이|가|도|만|서|로|와|과|며|고|어|아|해|게)$")
_LOCATION_SUFFIX = re.compile(r"[가-힣]{1,5}(?:구|시|군|동|읍|면|로|역)$")
_HANGUL_MIN2 = re.compile(r"[가-힣]{2,}")
_CANDIDATE_SANITIZE = re.compile(u"["'“”‘’·\[\]\(\)\{\}#@]")


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


def _extract_candidates_from_text(text: str, context: str) -> set[str]:
    candidates: set[str] = set()
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

def _parse_freshness(postdate: str | None) -> float:
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


def _compute_scores(aggregator: dict[str, dict]) -> list[dict]:
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
         for e in scored],
        key=lambda x: x["score"],
        reverse=True,
    )[:_TOP_N]


# ── 인기 수집 ──────────────────────────────────────────────────────────

async def extract_popular_names(context: str) -> list[dict]:
    """context별 Naver 블로그 검색 → 상호명 집계 → 점수 정규화."""
    normalized = _normalize_context(context)
    queries = _CONTEXT_QUERIES.get(normalized, [])
    if not queries:
        return []

    all_items: list[dict] = []
    for query in queries:
        try:
            items = await search_naver_blog(query, display=100, sort="sim")
            all_items.extend(items)
        except Exception as exc:
            _log.warning("blog extract failed context=%s query=%r err=%s", normalized, query, exc)

    # 전역 link dedupe
    seen_links: set[str] = set()
    unique_items: list[dict] = []
    for item in all_items:
        link = item.get("link", "")
        if link and link not in seen_links:
            seen_links.add(link)
            unique_items.append(item)

    aggregator: dict[str, dict] = {}
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


async def save_popular(context: str, results: list[dict]) -> None:
    if not results:
        return
    r = get_redis()
    key = f"popular:{context}"
    await r.setex(key, POPULAR_TTL, json.dumps(results, ensure_ascii=False))
    _log.info("popular saved context=%s count=%d ttl=%d", context, len(results), POPULAR_TTL)


async def collect_popular_for_context(context: str) -> list[dict]:
    normalized = _normalize_context(context)
    return await extract_popular_names(normalized)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_score.py tests/test_blog.py -v
```

Expected: 모두 PASS

- [ ] **Step 5: grooming_blog.py + 구 테스트 삭제**

```bash
rm app/ingestion/grooming_blog.py tests/test_grooming_blog.py
```

- [ ] **Step 6: Commit**

```bash
git add app/ingestion/blog.py tests/test_blog.py
git commit -m "feat(blog): extract_popular_names·save_popular 구현, grooming_blog.py 대체"
```

---

### Task 7: popular.py — GET /popular/{context} API

**Files:**
- Create: `app/serving/api/popular.py`
- Create: `app/platform/schemas/popular.py`
- Create: `tests/test_popular_api.py`
- Modify: `app/main.py` (popular_router 추가)

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_popular_api.py
import pytest
import json
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.fixture
def app():
    from app.main import app
    return app


@pytest.mark.asyncio
async def test_get_popular_returns_data(app):
    data = [{"name": "해피독", "mention_count": 5, "avg_freshness": 0.8, "score": 1.0}]
    with patch("app.serving.api.popular.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(data).encode())
        mock_get_redis.return_value = mock_redis
        with patch("app.platform.core.auth.settings") as mock_settings:
            mock_settings.API_KEY_HASH = __import__("hashlib").sha256(b"testkey").hexdigest()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/popular/grooming", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "해피독"


@pytest.mark.asyncio
async def test_get_popular_unknown_context_404(app):
    with patch("app.platform.core.auth.settings") as mock_settings:
        mock_settings.API_KEY_HASH = __import__("hashlib").sha256(b"testkey").hexdigest()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/popular/unknown_xyz", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_popular_redis_miss_503(app):
    with patch("app.serving.api.popular.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_get_redis.return_value = mock_redis
        with patch("app.platform.core.auth.settings") as mock_settings:
            mock_settings.API_KEY_HASH = __import__("hashlib").sha256(b"testkey").hexdigest()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/popular/grooming", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_get_popular_alias_snack_to_supplies(app):
    data = [{"name": "사료왕", "mention_count": 3, "avg_freshness": 0.7, "score": 1.0}]
    with patch("app.serving.api.popular.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(data).encode())
        mock_get_redis.return_value = mock_redis
        with patch("app.platform.core.auth.settings") as mock_settings:
            mock_settings.API_KEY_HASH = __import__("hashlib").sha256(b"testkey").hexdigest()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/popular/snack", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 200
    # snack → popular:supplies 키에서 읽음
    mock_redis.get.assert_called_with("popular:supplies")


@pytest.mark.asyncio
async def test_get_popular_limit_param(app):
    data = [{"name": f"미용실{i}", "mention_count": 5-i, "avg_freshness": 0.8, "score": 1.0-i*0.1}
            for i in range(10)]
    with patch("app.serving.api.popular.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(data).encode())
        mock_get_redis.return_value = mock_redis
        with patch("app.platform.core.auth.settings") as mock_settings:
            mock_settings.API_KEY_HASH = __import__("hashlib").sha256(b"testkey").hexdigest()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/popular/grooming?limit=3", headers={"X-API-Key": "testkey"})
    assert resp.status_code == 200
    assert len(resp.json()) == 3
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_popular_api.py -v
```

Expected: `ImportError` — `app.serving.api.popular` not found

- [ ] **Step 3: popular.py 구현**

```python
# app/platform/schemas/popular.py
from pydantic import BaseModel


class PopularEntry(BaseModel):
    name: str
    mention_count: int
    avg_freshness: float
    score: float
```

```python
# app/serving/api/popular.py
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from redis.exceptions import RedisError
from app.platform.cache.redis import get_redis
from app.platform.core.auth import require_api_key
from app.platform.observability import get_request_id

router = APIRouter(prefix="/popular", tags=["인기 (Popular)"])
_log = logging.getLogger(__name__)

_VALID_CONTEXTS = frozenset({
    "grooming", "hospital", "supplies", "pharmacy",
    "cafe", "pension", "restaurant", "boarding", "hotel",
})
_CONTEXT_ALIASES = {"snack": "supplies", "food": "supplies", "clothes": "supplies"}


@router.get(
    "/{context}",
    summary="컨텍스트별 인기 상호 (Popular businesses by context)",
    description="Naver 블로그 언급 기반 인기 상호 목록 (최대 20개). "
                "Redis `popular:{context}` 키에서 읽음.",
)
async def get_popular(
    request: Request,
    context: str = Path(..., description="grooming | hospital | supplies | pharmacy | cafe | pension | restaurant | boarding | hotel"),
    limit: int = Query(20, ge=1, le=20, description="반환 상한 (max 20)"),
    _: None = Depends(require_api_key),
):
    rid = get_request_id(request)
    normalized = _CONTEXT_ALIASES.get(context, context)
    if normalized not in _VALID_CONTEXTS:
        _log.info("[%s] get_popular context=%s -> 404 unknown", rid, context)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown context: {context}")

    key = f"popular:{normalized}"
    try:
        r = get_redis()
        raw = await r.get(key)
    except RedisError as e:
        _log.warning("[%s] get_popular context=%s -> 503 Redis error %s", rid, normalized, e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="popular data unavailable")

    if raw is None:
        _log.warning("[%s] get_popular context=%s -> 503 no data", rid, normalized)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="popular data unavailable")

    data: list[dict] = json.loads(raw)
    _log.info("[%s] get_popular context=%s -> count=%d limit=%d", rid, normalized, len(data), limit)
    return data[:limit]
```

- [ ] **Step 4: main.py에 popular_router 추가**

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.serving.api.collect import router as collect_router
from app.serving.api.trends import router as trends_router
from app.serving.api.popular import router as popular_router
from app.platform.scheduler.jobs import start_scheduler, stop_scheduler
from app.platform.observability import attach_observability


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Popularity Intelligence API (Pet Data API)",
    description=(
        "Naver 블로그 기반 반려동물 서비스 인기도 API "
        "(Popularity intelligence from blog mentions)"
    ),
    lifespan=lifespan,
)
attach_observability(app)
app.include_router(popular_router)
app.include_router(collect_router)
app.include_router(trends_router)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/test_popular_api.py -v
```

Expected: 모두 PASS

- [ ] **Step 6: Commit**

```bash
git add app/serving/api/popular.py app/platform/schemas/popular.py \
        app/main.py tests/test_popular_api.py
git commit -m "feat(api): GET /popular/{context} 엔드포인트 구현"
```

---

### Task 8: runner.py + jobs.py — popular 배치 추가

**Files:**
- Modify: `app/ingestion/runner.py` (run_popular_collection 추가)
- Modify: `app/platform/scheduler/jobs.py` (popular job 18:10)

- [ ] **Step 1: runner.py에 run_popular_collection 추가**

```python
# app/ingestion/runner.py
import logging
from app.ingestion.naver import collect_category_trends, CATEGORY_KEYWORDS
from app.ingestion.analyzer.trend import aggregate_keywords
from app.ingestion.blog import collect_popular_for_context, save_popular
from app.platform.cache.redis import save_trend

_log = logging.getLogger(__name__)

_POPULAR_CONTEXTS = [
    "grooming", "hospital", "supplies", "pharmacy",
    "cafe", "pension", "restaurant", "boarding", "hotel",
]


async def run_trend_collection() -> list[dict]:
    results = []
    for category in CATEGORY_KEYWORDS:
        try:
            items = await collect_category_trends(category)
            counts = aggregate_keywords(items)
            await save_trend(category, dict(counts))
            results.append({"category": category, "status": "success", "keywords_count": len(counts)})
        except Exception as e:
            _log.error("trend collection failed category=%s err=%s", category, e)
            results.append({"category": category, "status": "failed", "error_message": str(e)})
    return results


async def run_popular_collection() -> list[dict]:
    results = []
    for context in _POPULAR_CONTEXTS:
        try:
            popular = await collect_popular_for_context(context)
            await save_popular(context, popular)
            results.append({"context": context, "status": "success", "count": len(popular)})
        except Exception as e:
            _log.error("popular collection failed context=%s err=%s", context, e)
            results.append({"context": context, "status": "failed", "error_message": str(e)})
    return results
```

- [ ] **Step 2: jobs.py에 popular job 추가 (18:10)**

```python
# app/platform/scheduler/jobs.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.ingestion.runner import run_trend_collection, run_popular_collection

scheduler = AsyncIOScheduler()


def start_scheduler():
    scheduler.add_job(
        run_trend_collection,
        trigger="cron",
        hour=18,
        minute=0,
        max_instances=1,
        id="daily_trend_collection",
    )
    scheduler.add_job(
        run_popular_collection,
        trigger="cron",
        hour=18,
        minute=10,
        max_instances=1,
        id="daily_popular_collection",
    )
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
```

- [ ] **Step 3: 임포트 검증**

```bash
python -c "from app.ingestion.runner import run_trend_collection, run_popular_collection; print('OK')"
python -c "from app.platform.scheduler.jobs import start_scheduler; print('OK')"
```

Expected: 모두 `OK`

- [ ] **Step 4: Commit**

```bash
git add app/ingestion/runner.py app/platform/scheduler/jobs.py
git commit -m "feat(runner): run_popular_collection 추가, popular 스케줄 18:10 등록"
```

---

### Task 9: collect.py — targets body param 재작성

**Files:**
- Modify: `app/serving/api/collect.py`
- Create: `tests/test_collect_api.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_collect_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.fixture
def app():
    from app.main import app
    return app


def _admin_headers():
    import hashlib
    return {"X-ADMIN-API-Key": "adminkey"}


@pytest.mark.asyncio
async def test_trigger_collection_popular_only(app):
    with patch("app.serving.api.collect.run_popular_collection", new=AsyncMock()) as mock_popular, \
         patch("app.serving.api.collect.run_trend_collection", new=AsyncMock()) as mock_trends, \
         patch("app.platform.core.auth.settings") as mock_settings:
        mock_settings.ADMIN_API_KEY_HASH = __import__("hashlib").sha256(b"adminkey").hexdigest()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/collect/trigger",
                json={"targets": ["popular"]},
                headers=_admin_headers(),
            )
    assert resp.status_code == 202
    assert "popular" in resp.json()["targets"]


@pytest.mark.asyncio
async def test_trigger_collection_trends_only(app):
    with patch("app.serving.api.collect.run_trend_collection", new=AsyncMock()), \
         patch("app.platform.core.auth.settings") as mock_settings:
        mock_settings.ADMIN_API_KEY_HASH = __import__("hashlib").sha256(b"adminkey").hexdigest()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/collect/trigger",
                json={"targets": ["trends"]},
                headers=_admin_headers(),
            )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_trigger_collection_both(app):
    with patch("app.serving.api.collect.run_popular_collection", new=AsyncMock()), \
         patch("app.serving.api.collect.run_trend_collection", new=AsyncMock()), \
         patch("app.platform.core.auth.settings") as mock_settings:
        mock_settings.ADMIN_API_KEY_HASH = __import__("hashlib").sha256(b"adminkey").hexdigest()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/collect/trigger",
                json={"targets": ["popular", "trends"]},
                headers=_admin_headers(),
            )
    assert resp.status_code == 202
    assert set(resp.json()["targets"]) == {"popular", "trends"}


@pytest.mark.asyncio
async def test_trigger_collection_invalid_target_422(app):
    with patch("app.platform.core.auth.settings") as mock_settings:
        mock_settings.ADMIN_API_KEY_HASH = __import__("hashlib").sha256(b"adminkey").hexdigest()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/collect/trigger",
                json={"targets": ["invalid_target"]},
                headers=_admin_headers(),
            )
    assert resp.status_code == 422
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_collect_api.py -v
```

Expected: 일부 FAIL (현재 collect.py는 stub)

- [ ] **Step 3: collect.py 재작성**

```python
# app/serving/api/collect.py
import logging
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from pydantic import BaseModel
from app.platform.core.auth import require_admin_key
from app.platform.observability import get_request_id
from app.ingestion.runner import run_popular_collection, run_trend_collection

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/collect", tags=["관리자 (Admin)"])


class CollectRequest(BaseModel):
    targets: list[Literal["popular", "trends"]]


@router.post(
    "/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="수집 실행 (Trigger collection)",
    description="popular·trends 중 지정한 배치를 백그라운드로 즉시 실행. 관리자 API 키 필요.",
    response_model=dict,
)
async def trigger_collection(
    request: Request,
    background_tasks: BackgroundTasks,
    body: CollectRequest,
    _: None = Depends(require_admin_key),
):
    rid = get_request_id(request)
    _log.info("[%s] trigger_collection targets=%s", rid, body.targets)
    for target in body.targets:
        if target == "popular":
            background_tasks.add_task(run_popular_collection)
        elif target == "trends":
            background_tasks.add_task(run_trend_collection)
    return {"message": "collection started", "targets": body.targets}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_collect_api.py -v
```

Expected: 모두 PASS

- [ ] **Step 5: 전체 테스트 실행**

```bash
pytest tests/ -v --ignore=tests/test_grooming_blog.py 2>&1 | tail -20
```

Expected: 실패 없음 (혹은 남은 파일 import 문제만)

- [ ] **Step 6: Commit**

```bash
git add app/serving/api/collect.py tests/test_collect_api.py
git commit -m "feat(collect): targets body param으로 popular·trends 배치 선택 지원"
```

---

### Task 10: 외부 문서 정리

**Files:**
- Delete: `docs/GROOMING-RECOMMEND-MVP.md`
- Delete: `docs/INGESTION-VS-SERVING.md`
- Modify: `docs/PROJECT-OVERVIEW.md` (엔드포인트·기술 스택 전면 재작성)
- Modify: `docs/USAGE.md` (`/recommend`, `/facilities` 예시 제거, `/popular` 예시 추가)
- Modify: `docs/ARCHITECTURE.md` (시스템 구조 재작성)
- Modify: `docs/PETORY-INTEGRATION.md` (`/recommend` → `/popular` + `/trends`)
- Modify: `docs/V3-CHANGES.md` (이번 재설계로 교체)
- Modify: `CLAUDE.md` (엔드포인트 표·기술 스택 수정)

- [ ] **Step 1: 삭제**

```bash
rm docs/GROOMING-RECOMMEND-MVP.md docs/INGESTION-VS-SERVING.md
```

- [ ] **Step 2: docs/PROJECT-OVERVIEW.md 핵심 섹션 업데이트**

엔드포인트 표를 아래로 교체:

```markdown
## API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/popular/{context}` | 컨텍스트별 인기 상호 목록 | 일반 |
| GET | `/trends/{category}` | 트렌드 키워드 | 일반 |
| POST | `/collect/trigger` | popular·trends 배치 즉시 실행 | 관리자 |

context: grooming, hospital, supplies, pharmacy, cafe, pension, restaurant, boarding, hotel
```

기술 스택에서 PostgreSQL, Kakao, LLM (Ollama), `POST /recommend` 관련 항목 제거.

- [ ] **Step 3: docs/USAGE.md 업데이트**

`/recommend`, `/facilities`, `/stats` curl 예시 제거. 아래 예시 추가:

```markdown
## 인기 상호 조회

curl -H "X-API-Key: $API_KEY" http://localhost:8000/popular/grooming

## 배치 수동 실행 (관리자)

curl -X POST -H "X-ADMIN-API-Key: $ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{"targets": ["popular", "trends"]}' \
     http://localhost:8000/collect/trigger
```

실행 섹션에서 PostgreSQL 설치·마이그레이션 단계 제거. `.env` 예시에서 `DATABASE_URL`, `KAKAO_*`, `OLLAMA_*` 제거.

- [ ] **Step 4: docs/ARCHITECTURE.md 재작성**

```markdown
# Architecture

## 시스템 구조

매일 18:00 트렌드 배치, 18:10 인기 배치:

```
Naver Blog API
    ↓ (trends) collect_category_trends → aggregate_keywords → Redis trends:{category}:keywords
    ↓ (popular) extract_popular_names → _compute_scores → Redis popular:{context}
```

Petory 흐름:
```
사용자 요청
  → Petory: 자체 DB에서 주변 시설 조회
  → Petory: GET /popular/{context}   (Python 서버)
  → Petory: GET /trends/{category}   (Python 서버)
  → UI: 시설 목록 + 인기 뱃지 + 트렌드 키워드
```
```

- [ ] **Step 5: docs/PETORY-INTEGRATION.md 업데이트**

`POST /recommend` 단일 호출 → `GET /popular/{context}` + `GET /trends/{category}` 두 호출로 변경 설명 업데이트.

- [ ] **Step 6: docs/V3-CHANGES.md 업데이트**

이번 재설계 내용으로 교체:
- 제거: PostgreSQL, Kakao Local API, Ollama LLM, `POST /recommend`, 공공 시설 수집
- 추가: `GET /popular/{context}`, `app/ingestion/blog.py`, Redis `popular:{context}` 키 (TTL 25h)
- 변경: `POST /collect/trigger` body `targets` 파라미터, popular 스케줄 18:10

- [ ] **Step 7: CLAUDE.md 업데이트**

엔드포인트 요약표에서 `/facilities`, `/stats`, `/recommend` 제거, `/popular/{context}` 추가.

기술 스택에서 PostgreSQL, SQLAlchemy, `pg_trgm` 제거. Kakao, LLM 제거.

환경변수 예시에서 `DATABASE_URL`, `KAKAO_*`, `OLLAMA_*`, `GROOMING_MVP_ENABLED` 제거.

프로젝트 구조 업데이트: `ingestion/blog.py` 추가, 삭제 파일 반영, `serving/api/popular.py` 추가.

- [ ] **Step 8: 최종 전체 테스트**

```bash
pytest tests/ -v 2>&1 | tail -30
```

Expected: 실패 없음

- [ ] **Step 9: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs: Popularity Intelligence 재설계 반영 — 외부 문서 일괄 정리"
```

---

## 셀프 리뷰

**스펙 커버리지:**
- §2 시스템 구조: Task 7 (popular.py), Task 8 (jobs.py) ✓
- §3 score 수식: Task 5 (_compute_scores, _parse_freshness TDD) ✓
- §3 max=0 엣지 케이스: Task 5 (`test_compute_scores_all_stale_returns_empty`) ✓
- §4 배치 파이프라인: Task 6 (extract_popular_names, 전역 dedupe), Task 8 (runner) ✓
- §4 supplies 8쿼리: Task 6 (_CONTEXT_QUERIES supplies = 4 categories × 2 queries) ✓
- §4 실패 처리: Task 6 (save_popular — 빈 결과 skip), Task 8 (per-context try/except) ✓
- §5 context↔category 매핑: Task 7 (_CONTEXT_ALIASES, _VALID_CONTEXTS) ✓
- §6 GET /popular/{context}: Task 7 ✓
- §6 GET /trends/{category} 변경 없음 (timeseries만 삭제): Task 2 ✓
- §6 POST /collect/trigger targets body: Task 9 ✓
- §7 client.py 인라인 → 삭제: Task 3 ✓
- §7 grooming_blog.py → blog.py: Task 6 ✓
- §7 config.py 설정 제거: Task 4 ✓
- §8 테스트 신규/삭제: test_score.py (Task 5), test_blog.py (Task 6), test_popular_api.py (Task 7), test_collect_api.py (Task 9) ✓
- §9 외부 문서: Task 10 ✓

**타입 일관성:**
- `aggregator: dict[str, dict]` → Task 5 `_compute_scores`, Task 6 `extract_popular_names` 동일 ✓
- `save_popular(context: str, results: list[dict])` → Task 6 구현, Task 8 호출 ✓
- `POPULAR_TTL` → Task 6에서 정의, Task 7 테스트에서 import 검증 ✓
- `run_popular_collection()` → Task 8 정의, Task 9 collect.py import ✓
