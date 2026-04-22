# Pet Trend Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 블로그 검색 API에서 반려동물 관련 텍스트를 수집하고 형태소 분석으로 인기 키워드를 추출해 Redis에 캐싱, REST API로 제공한다.

**Architecture:** 기존 공공API 수집 파이프라인(시설 정보)과 독립적으로, 네이버 API → 형태소 분석 → Redis Sorted Set → `/trends/{category}` API 레이어를 추가한다. 코드 정리(유기동물 제거, retry 중복 제거)를 선행 작업으로 수행한다.

**Tech Stack:** FastAPI, httpx, kiwipiepy, redis-py(async), APScheduler, PostgreSQL(기존 유지)

---

## File Map

| 작업 | 파일 |
|------|------|
| **삭제** | `app/collector/parser.py` |
| **삭제** | `app/models/animal.py` |
| **삭제** | `app/api/animals.py` |
| **삭제** | `app/schemas/animal.py` |
| **생성** | `migrations/002_drop_abandoned_animals.sql` |
| **수정** | `app/collector/client.py` — params optional화 |
| **수정** | `app/collector/business.py` — client.py 사용 |
| **수정** | `app/collector/hospital.py` — client.py 사용 |
| **수정** | `app/core/config.py` — Naver/Redis 환경변수 추가 |
| **수정** | `requirements.txt` — kiwipiepy, redis 추가 |
| **생성** | `app/collector/naver.py` — 네이버 블로그 검색 API |
| **생성** | `app/analyzer/__init__.py` |
| **생성** | `app/analyzer/morpheme.py` — kiwipiepy 명사 추출 |
| **생성** | `app/analyzer/trend.py` — 키워드 빈도 집계 |
| **생성** | `app/cache/__init__.py` |
| **생성** | `app/cache/redis.py` — Redis Sorted Set CRUD |
| **수정** | `app/collector/runner.py` — run_trend_collection() 추가 |
| **수정** | `app/scheduler/jobs.py` — 03:00 트렌드 수집 잡 추가 |
| **생성** | `app/api/trends.py` — GET /trends/{category} |
| **수정** | `app/main.py` — trends 라우터 등록 |
| **생성** | `tests/test_naver_collector.py` |
| **생성** | `tests/test_analyzer.py` |
| **생성** | `tests/test_trends_api.py` |

---

## Task 1: 유기동물 코드 제거

**Files:**
- Delete: `app/collector/parser.py`
- Delete: `app/models/animal.py`
- Delete: `app/api/animals.py`
- Delete: `app/schemas/animal.py`
- Create: `migrations/002_drop_abandoned_animals.sql`

- [ ] **Step 1: 파일 삭제**

```bash
rm app/collector/parser.py
rm app/models/animal.py
rm app/api/animals.py
rm app/schemas/animal.py
```

- [ ] **Step 2: Drop migration 작성**

`migrations/002_drop_abandoned_animals.sql` 내용:

```sql
DROP MATERIALIZED VIEW IF EXISTS mv_region_stats;
DROP TABLE IF EXISTS abandoned_animals;
```

- [ ] **Step 3: 테스트 삭제 (유기동물 관련)**

```bash
rm tests/test_models.py
rm tests/test_collector.py
```

> `test_collector.py`는 구버전 유기동물 수집 테스트. `test_business_collector.py`, `test_hospital_collector.py`는 유지.

- [ ] **Step 4: 서버 기동 확인**

```bash
uvicorn app.main:app --reload
```

Expected: `Application startup complete.` — ImportError 없어야 함.

- [ ] **Step 5: 커밋**

```bash
git add -A
git commit -m "chore: remove abandoned_animals — parser, model, api, schema, migration"
```

---

## Task 2: Retry 로직 client.py로 통합

**Files:**
- Modify: `app/collector/client.py`
- Modify: `app/collector/business.py`
- Modify: `app/collector/hospital.py`
- Test: `tests/test_business_collector.py`

- [ ] **Step 1: 기존 테스트 실행 확인**

```bash
pytest tests/test_business_collector.py tests/test_hospital_collector.py -v
```

Expected: 모두 PASS (리팩토링 전 베이스라인 확인)

- [ ] **Step 2: client.py 수정 — params 선택적으로**

`app/collector/client.py` 전체 교체:

```python
import asyncio
import httpx
from typing import Optional

RETRY_DELAYS = [1, 2, 4]


async def fetch_public_api(url: str, params: Optional[dict] = None, timeout: int = 30) -> dict:
    last_error: Optional[Exception] = None
    for delay in [0] + RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            last_error = e
    raise last_error
```

- [ ] **Step 3: business.py에서 중복 retry 제거**

`app/collector/business.py` 전체 교체:

```python
from urllib.parse import quote_plus
from app.core.config import settings
from app.collector.client import fetch_public_api

BUSINESS_API_URL = "https://apis.data.go.kr/1741000/pet_grooming/info"


def _parse_region(addr: str):
    parts = addr.split()
    city = parts[0] if len(parts) > 0 else ""
    district = parts[1] if len(parts) > 1 else ""
    return city, district


async def fetch_businesses(page: int = 1, num_of_rows: int = 1000) -> dict:
    key = quote_plus(settings.PUBLIC_DATA_API_KEY)
    url = f"{BUSINESS_API_URL}?serviceKey={key}&pageNo={page}&numOfRows={num_of_rows}"
    return await fetch_public_api(url)


def parse_business_item(raw: dict) -> dict:
    addr = raw.get("ROAD_NM_ADDR") or raw.get("LOTNO_ADDR", "")
    region_city, region_district = _parse_region(addr)
    return {
        "source_id": raw.get("MNG_NO", ""),
        "type": "BUSINESS",
        "name": raw.get("BPLC_NM", ""),
        "status": raw.get("SALS_STTS_NM", ""),
        "address": addr,
        "region_city": region_city,
        "region_district": region_district,
        "phone": raw.get("TELNO") or None,
        "business_type": "동물미용업",
        "registration_no": raw.get("MNG_NO") or None,
    }


def extract_businesses(response: dict) -> list:
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_business_item(item) for item in items]
    except (KeyError, TypeError):
        return []
```

- [ ] **Step 4: hospital.py에서 중복 retry 제거**

`app/collector/hospital.py` 전체 교체:

```python
from urllib.parse import quote_plus
from app.core.config import settings
from app.collector.client import fetch_public_api

HOSPITAL_API_URL = "https://apis.data.go.kr/1741000/animal_hospitals/info"


def _parse_region(addr: str):
    parts = addr.split()
    city = parts[0] if len(parts) > 0 else ""
    district = parts[1] if len(parts) > 1 else ""
    return city, district


async def fetch_hospitals(page: int = 1, num_of_rows: int = 1000) -> dict:
    key = quote_plus(settings.HOSPITAL_API_KEY)
    url = f"{HOSPITAL_API_URL}?serviceKey={key}&pageNo={page}&numOfRows={num_of_rows}"
    return await fetch_public_api(url)


def parse_hospital_item(raw: dict) -> dict:
    addr = raw.get("ROAD_NM_ADDR") or raw.get("LOTNO_ADDR", "")
    region_city, region_district = _parse_region(addr)
    return {
        "source_id": raw.get("MNG_NO", ""),
        "type": "HOSPITAL",
        "name": raw.get("BPLC_NM", ""),
        "status": raw.get("SALS_STTS_NM", ""),
        "address": addr,
        "region_city": region_city,
        "region_district": region_district,
        "phone": raw.get("TELNO") or None,
        "license_no": raw.get("LCPMT_YMD") or None,
        "specialty": raw.get("DTL_TASK_SE_NM") or None,
    }


def extract_hospitals(response: dict) -> list:
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_hospital_item(item) for item in items]
    except (KeyError, TypeError):
        return []
```

- [ ] **Step 5: 기존 테스트 재실행**

```bash
pytest tests/test_business_collector.py tests/test_hospital_collector.py -v
```

Expected: 모두 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/collector/client.py app/collector/business.py app/collector/hospital.py
git commit -m "refactor: consolidate retry logic into client.py"
```

---

## Task 3: 환경변수 및 의존성 추가

**Files:**
- Modify: `app/core/config.py`
- Modify: `requirements.txt`

- [ ] **Step 1: config.py에 신규 환경변수 추가**

`app/core/config.py` 전체 교체:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    API_KEY_HASH: str
    ADMIN_API_KEY_HASH: str
    PUBLIC_DATA_API_KEY: str
    HOSPITAL_API_KEY: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 2: .env에 신규 키 추가 (로컬 개발용)**

`.env` 파일에 아래 줄 추가 (실제 값은 직접 입력):

```
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret
REDIS_URL=redis://localhost:6379/0
```

> 네이버 개발자센터(developers.naver.com)에서 "검색" API 애플리케이션 등록 후 발급.

- [ ] **Step 3: requirements.txt에 패키지 추가**

`requirements.txt` 전체 교체:

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
httpx==0.27.0
apscheduler==3.10.4
pydantic-settings==2.5.2
python-dotenv==1.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
kiwipiepy>=0.20.0
redis>=5.0.0
```

- [ ] **Step 4: 패키지 설치**

```bash
pip install kiwipiepy redis
```

Expected: 설치 완료. `kiwipiepy` 첫 실행 시 모델 다운로드 (약 100MB, 자동).

- [ ] **Step 5: 서버 기동 확인**

```bash
uvicorn app.main:app --reload
```

Expected: `Application startup complete.` — Settings validation 에러 없어야 함.

- [ ] **Step 6: 커밋**

```bash
git add app/core/config.py requirements.txt
git commit -m "chore: add Naver API and Redis config + dependencies"
```

---

## Task 4: 네이버 블로그 검색 수집기

**Files:**
- Create: `app/collector/naver.py`
- Test: `tests/test_naver_collector.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_naver_collector.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.collector.naver import search_naver_blog, collect_category_trends, CATEGORY_KEYWORDS


@pytest.mark.asyncio
async def test_search_naver_blog_returns_items():
    mock_response = {
        "items": [
            {"title": "강아지 <b>간식</b> 추천 TOP5", "description": "오리젠 로얄캐닌 후기"},
            {"title": "고양이 간식 후기", "description": "퍼스트메이트 정보"},
        ]
    }
    with patch("app.collector.naver.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_response_obj = AsyncMock()
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.raise_for_status = AsyncMock()
        mock_client.get.return_value = mock_response_obj

        items = await search_naver_blog("강아지 간식 추천")

    assert len(items) == 2
    assert items[0]["title"] == "강아지 <b>간식</b> 추천 TOP5"


@pytest.mark.asyncio
async def test_collect_category_trends_merges_queries():
    mock_items = [{"title": "test", "description": "desc"}]
    with patch("app.collector.naver.search_naver_blog", return_value=mock_items):
        result = await collect_category_trends("snack")

    queries = CATEGORY_KEYWORDS["snack"]
    assert len(result) == len(queries) * len(mock_items)


def test_category_keywords_has_required_categories():
    required = {"snack", "food", "grooming", "hospital", "clothes"}
    assert required.issubset(set(CATEGORY_KEYWORDS.keys()))
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/test_naver_collector.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.collector.naver'`

- [ ] **Step 3: naver.py 구현**

`app/collector/naver.py`:

```python
import re
import httpx
from app.core.config import settings

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
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(NAVER_BLOG_URL, headers=headers, params=params)
        response.raise_for_status()
        items = response.json().get("items", [])
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
```

- [ ] **Step 4: 테스트 재실행 — PASS 확인**

```bash
pytest tests/test_naver_collector.py -v
```

Expected: 3개 PASS

- [ ] **Step 5: 커밋**

```bash
git add app/collector/naver.py tests/test_naver_collector.py
git commit -m "feat: add Naver blog search collector"
```

---

## Task 5: 형태소 분석기

**Files:**
- Create: `app/analyzer/__init__.py`
- Create: `app/analyzer/morpheme.py`
- Create: `app/analyzer/trend.py`
- Test: `tests/test_analyzer.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_analyzer.py`:

```python
from collections import Counter
from app.analyzer.morpheme import extract_nouns
from app.analyzer.trend import aggregate_keywords


def test_extract_nouns_returns_nouns():
    text = "강아지 간식 오리젠 추천 후기"
    nouns = extract_nouns(text)
    assert "오리젠" in nouns


def test_extract_nouns_filters_stopwords():
    text = "강아지 고양이 반려동물 추천 후기 정보"
    nouns = extract_nouns(text)
    # 불용어는 결과에 없어야 함
    stopwords = {"강아지", "고양이", "반려동물", "추천", "후기", "정보"}
    assert not stopwords.intersection(set(nouns))


def test_extract_nouns_filters_single_char():
    text = "개 고양이 밥 먹기"
    nouns = extract_nouns(text)
    assert all(len(n) > 1 for n in nouns)


def test_aggregate_keywords_counts_frequency():
    items = [
        {"title": "오리젠 간식 후기", "description": "오리젠 추천"},
        {"title": "로얄캐닌 사료", "description": "오리젠 비교"},
    ]
    counter = aggregate_keywords(items)
    assert isinstance(counter, Counter)
    assert counter["오리젠"] >= 2


def test_aggregate_keywords_empty_input():
    counter = aggregate_keywords([])
    assert len(counter) == 0
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/test_analyzer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: morpheme.py 구현**

`app/analyzer/__init__.py`: (빈 파일)

`app/analyzer/morpheme.py`:

```python
from kiwipiepy import Kiwi

_kiwi = Kiwi()

STOPWORDS = {
    "강아지", "고양이", "반려동물", "반려", "추천", "후기", "정보",
    "소개", "리뷰", "구매", "사용", "사용기", "제품", "브랜드",
}


def extract_nouns(text: str) -> list[str]:
    tokens = _kiwi.tokenize(text)
    return [
        t.form
        for t in tokens
        if t.tag in ("NNG", "NNP") and t.form not in STOPWORDS and len(t.form) > 1
    ]
```

- [ ] **Step 4: trend.py 구현**

`app/analyzer/trend.py`:

```python
from collections import Counter
from app.analyzer.morpheme import extract_nouns


def aggregate_keywords(items: list[dict]) -> Counter:
    counter: Counter = Counter()
    for item in items:
        text = f"{item.get('title', '')} {item.get('description', '')}"
        counter.update(extract_nouns(text))
    return counter
```

- [ ] **Step 5: 테스트 재실행 — PASS 확인**

```bash
pytest tests/test_analyzer.py -v
```

Expected: 5개 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/analyzer/ tests/test_analyzer.py
git commit -m "feat: add morpheme analyzer with kiwipiepy"
```

---

## Task 6: Redis 캐시 레이어

**Files:**
- Create: `app/cache/__init__.py`
- Create: `app/cache/redis.py`

- [ ] **Step 1: redis.py 구현**

`app/cache/__init__.py`: (빈 파일)

`app/cache/redis.py`:

```python
from datetime import datetime, timezone
import redis.asyncio as aioredis
from app.core.config import settings

_redis: aioredis.Redis | None = None

TREND_KEY = "trends:{category}:keywords"
UPDATED_KEY = "trends:{category}:updated_at"
TTL = 86400  # 24h


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def save_trend(category: str, keyword_counts: dict[str, int]) -> None:
    r = get_redis()
    key = TREND_KEY.format(category=category)
    updated_key = UPDATED_KEY.format(category=category)
    async with r.pipeline() as pipe:
        pipe.delete(key)
        if keyword_counts:
            pipe.zadd(key, keyword_counts)
        pipe.setex(updated_key, TTL, datetime.now(timezone.utc).isoformat())
        pipe.expire(key, TTL)
        await pipe.execute()


async def get_trend(category: str, limit: int = 20) -> list[tuple[str, float]]:
    r = get_redis()
    key = TREND_KEY.format(category=category)
    return await r.zrange(key, 0, limit - 1, desc=True, withscores=True)


async def get_updated_at(category: str) -> str | None:
    r = get_redis()
    return await r.get(UPDATED_KEY.format(category=category))
```

- [ ] **Step 2: Redis 연결 수동 확인**

로컬에 Redis가 실행 중이어야 함:

```bash
redis-cli ping
```

Expected: `PONG`

Redis 미설치 시: `brew install redis && brew services start redis`

- [ ] **Step 3: save/get 동작 확인 (Python REPL)**

```bash
python3 -c "
import asyncio
from app.cache.redis import save_trend, get_trend
async def test():
    await save_trend('snack', {'오리젠': 10, '로얄캐닌': 7})
    result = await get_trend('snack', 5)
    print(result)
asyncio.run(test())
"
```

Expected: `[('오리젠', 10.0), ('로얄캐닌', 7.0)]`

- [ ] **Step 4: 커밋**

```bash
git add app/cache/
git commit -m "feat: add Redis cache layer for trend storage"
```

---

## Task 7: 트렌드 수집 러너 + 스케줄러

**Files:**
- Modify: `app/collector/runner.py`
- Modify: `app/scheduler/jobs.py`

- [ ] **Step 1: runner.py에 run_trend_collection() 추가**

`app/collector/runner.py` 하단에 추가 (기존 코드 유지):

```python
from app.collector.naver import collect_category_trends, CATEGORY_KEYWORDS
from app.analyzer.trend import aggregate_keywords
from app.cache.redis import save_trend


async def run_trend_collection() -> list[dict]:
    results = []
    for category in CATEGORY_KEYWORDS:
        try:
            items = await collect_category_trends(category)
            counts = aggregate_keywords(items)
            await save_trend(category, dict(counts))
            results.append({
                "category": category,
                "status": "success",
                "keywords_count": len(counts),
            })
        except Exception as e:
            results.append({
                "category": category,
                "status": "failed",
                "error": str(e),
            })
    return results
```

- [ ] **Step 2: scheduler/jobs.py에 03:00 잡 추가**

`app/scheduler/jobs.py` 전체 교체:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import AsyncSessionLocal
from app.collector.runner import run_collection, run_trend_collection

scheduler = AsyncIOScheduler()


async def scheduled_collection():
    async with AsyncSessionLocal() as db:
        await run_collection(db)


async def scheduled_trend_collection():
    await run_trend_collection()


def start_scheduler():
    scheduler.add_job(
        scheduled_collection,
        trigger="cron",
        hour=2,
        minute=0,
        max_instances=1,
        id="daily_collection",
    )
    scheduler.add_job(
        scheduled_trend_collection,
        trigger="cron",
        hour=3,
        minute=0,
        max_instances=1,
        id="daily_trend_collection",
    )
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
```

- [ ] **Step 3: 서버 기동 확인**

```bash
uvicorn app.main:app --reload
```

Expected: `Application startup complete.` — 스케줄러 두 잡 등록 에러 없어야 함.

- [ ] **Step 4: 커밋**

```bash
git add app/collector/runner.py app/scheduler/jobs.py
git commit -m "feat: add trend collection runner and 03:00 scheduler job"
```

---

## Task 8: Trends API 엔드포인트

**Files:**
- Create: `app/api/trends.py`
- Modify: `app/main.py`
- Test: `tests/test_trends_api.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_trends_api.py`:

```python
import hashlib
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def patch_api_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.core.config.settings.ADMIN_API_KEY_HASH", "different_hash")


@pytest.mark.asyncio
async def test_get_trends_success():
    mock_keywords = [("오리젠", 10.0), ("로얄캐닌", 7.0)]
    mock_updated = "2026-04-21T03:05:00+00:00"

    with patch("app.api.trends.get_trend", new=AsyncMock(return_value=mock_keywords)), \
         patch("app.api.trends.get_updated_at", new=AsyncMock(return_value=mock_updated)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/trends/snack", headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "snack"
    assert data["keywords"][0]["keyword"] == "오리젠"
    assert data["keywords"][0]["score"] == 10


@pytest.mark.asyncio
async def test_get_trends_unknown_category():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/trends/unknown_cat", headers=HEADERS)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_trends_no_data_returns_503():
    with patch("app.api.trends.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.api.trends.get_updated_at", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/trends/snack", headers=HEADERS)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_get_trends_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/trends/snack")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_trends_limit_param():
    mock_keywords = [("오리젠", 10.0)]
    with patch("app.api.trends.get_trend", new=AsyncMock(return_value=mock_keywords)), \
         patch("app.api.trends.get_updated_at", new=AsyncMock(return_value="2026-04-21T03:05:00+00:00")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/trends/snack?limit=5", headers=HEADERS)
    assert response.status_code == 200
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/test_trends_api.py -v
```

Expected: FAIL — `ImportError` (trends 라우터 없음)

- [ ] **Step 3: trends.py 구현**

`app/api/trends.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.cache.redis import get_trend, get_updated_at
from app.core.auth import require_api_key
from app.collector.naver import CATEGORY_KEYWORDS

router = APIRouter(prefix="/trends", tags=["trends"])

VALID_CATEGORIES = set(CATEGORY_KEYWORDS.keys())


@router.get("/{category}")
async def get_trends(
    category: str,
    limit: int = Query(20, ge=1, le=50),
    _: None = Depends(require_api_key),
):
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown category: {category}")

    keywords = await get_trend(category, limit)
    if not keywords:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Trend data unavailable")

    updated_at = await get_updated_at(category)
    return {
        "category": category,
        "updated_at": updated_at,
        "keywords": [{"keyword": k, "score": int(s)} for k, s in keywords],
    }
```

- [ ] **Step 4: main.py에 라우터 등록**

`app/main.py` 전체 교체:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.facilities import router as facilities_router
from app.api.stats import router as stats_router
from app.api.collect import router as collect_router
from app.api.trends import router as trends_router
from app.scheduler.jobs import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Pet Data API", lifespan=lifespan)
app.include_router(facilities_router)
app.include_router(stats_router)
app.include_router(collect_router)
app.include_router(trends_router)
```

- [ ] **Step 5: 테스트 재실행 — PASS 확인**

```bash
pytest tests/test_trends_api.py -v
```

Expected: 5개 PASS

- [ ] **Step 6: 전체 테스트 실행**

```bash
pytest tests/ -v
```

Expected: 모두 PASS (삭제된 파일 관련 테스트 제외)

- [ ] **Step 7: Swagger UI 확인**

```bash
uvicorn app.main:app --reload
```

브라우저에서 `http://localhost:8000/docs` 열기.
`/trends/{category}` 엔드포인트가 표시되어야 함.

- [ ] **Step 8: 커밋**

```bash
git add app/api/trends.py app/main.py tests/test_trends_api.py
git commit -m "feat: add GET /trends/{category} endpoint"
```

---

## 완료 체크리스트

- [ ] `abandoned_animals` 관련 코드 전부 제거됨
- [ ] retry 로직이 `client.py` 한 곳에만 존재
- [ ] `GET /trends/{category}` — 5개 카테고리 동작
- [ ] Redis 미연결 시 503 반환 (graceful)
- [ ] APScheduler 잡 2개 등록: 02:00 시설, 03:00 트렌드
- [ ] 전체 테스트 PASS
