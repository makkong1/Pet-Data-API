# Naver Blog Trend Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `search_naver_blog`에 `sort` 파라미터를 추가하고, `collect_category_trends`를 `asyncio.gather` + 동적 세마포어 + link dedup으로 재작성해 date/sim 이중 수집과 중복 제거를 구현한다.

**Architecture:** `app/ingestion/naver.py` 단일 파일만 수정. `search_naver_blog`에 `sort` 인자 추가 후 기본값 `"sim"` 유지로 하위 호환. `collect_category_trends`는 `(query, sort)` 조합 전체를 `asyncio.gather`로 병렬 발화하고, 카테고리별 동적 세마포어(`max(1, min(8, len(queries)*2))`)로 동시 호출 상한 설정 후 `link` 기준 dedup.

**Tech Stack:** Python 3.9, asyncio, pytest-asyncio, `unittest.mock.AsyncMock`

---

## File Map

| 파일 | 작업 |
|------|------|
| `app/ingestion/naver.py` | `search_naver_blog` sort 파라미터 + blogger 필드 추가, `collect_category_trends` gather+semaphore+dedup 재작성 |
| `tests/test_naver_collector.py` | 신규 테스트 추가, 기존 `test_collect_category_trends_merges_queries` 업데이트 |

---

## Task 1: `search_naver_blog` — sort 파라미터 + blogger 필드

**Files:**
- Modify: `app/ingestion/naver.py:25-41`
- Test: `tests/test_naver_collector.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_naver_collector.py` 파일 끝에 아래 두 테스트를 추가한다.

```python
@pytest.mark.asyncio
async def test_search_naver_blog_passes_sort_to_params():
    mock_response = {"items": []}
    with patch("app.ingestion.naver.fetch_public_api", new=AsyncMock(return_value=mock_response)) as mock_fetch:
        await search_naver_blog("강아지 간식", sort="date")
    _, kwargs = mock_fetch.call_args
    assert kwargs["params"]["sort"] == "date"


@pytest.mark.asyncio
async def test_search_naver_blog_includes_blogger_fields():
    mock_response = {
        "items": [
            {
                "title": "강아지 <b>간식</b>",
                "description": "설명",
                "link": "https://blog.naver.com/post/1",
                "postdate": "20240101",
                "bloggername": "펫블로거",
                "bloggerlink": "https://blog.naver.com/petblog",
            }
        ]
    }
    with patch("app.ingestion.naver.fetch_public_api", new=AsyncMock(return_value=mock_response)):
        items = await search_naver_blog("강아지 간식")

    assert items[0]["blogger_name"] == "펫블로거"
    assert items[0]["blogger_link"] == "https://blog.naver.com/petblog"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/maknkkong/project/pet-data-api && ./venv/bin/pytest tests/test_naver_collector.py::test_search_naver_blog_passes_sort_to_params tests/test_naver_collector.py::test_search_naver_blog_includes_blogger_fields -v
```

기대 결과: 두 테스트 모두 `FAILED` — `sort` 파라미터 미지원, `blogger_name` 키 없음.

- [ ] **Step 3: `search_naver_blog` 구현**

`app/ingestion/naver.py`의 `search_naver_blog` 함수를 아래로 교체한다.

```python
async def search_naver_blog(query: str, display: int = 100, sort: str = "sim") -> list[dict]:
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": sort}
    data = await fetch_public_api(NAVER_BLOG_URL, params=params, headers=headers, timeout=10)
    items = data.get("items", [])
    return [
        {
            "title":        _strip_html(i.get("title", "")),
            "description":  _strip_html(i.get("description", "")),
            "link":         i.get("link", ""),
            "postdate":     i.get("postdate", ""),
            "blogger_name": i.get("bloggername", ""),
            "blogger_link": i.get("bloggerlink", ""),
        }
        for i in items
    ]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd /Users/maknkkong/project/pet-data-api && ./venv/bin/pytest tests/test_naver_collector.py -v
```

기대 결과: 기존 3개 포함 5개 모두 `PASSED`.

- [ ] **Step 5: 커밋**

```bash
cd /Users/maknkkong/project/pet-data-api && git add app/ingestion/naver.py tests/test_naver_collector.py && git commit -m "feat(naver): search_naver_blog에 sort 파라미터 + blogger 필드 추가"
```

---

## Task 2: `collect_category_trends` — gather + 동적 세마포어 + link dedup

**Files:**
- Modify: `app/ingestion/naver.py:1-5` (import 추가), `app/ingestion/naver.py:43-48` (함수 재작성)
- Test: `tests/test_naver_collector.py`

- [ ] **Step 1: 기존 테스트 업데이트 + 신규 실패 테스트 작성**

`tests/test_naver_collector.py`에서 `test_collect_category_trends_merges_queries`를 아래로 교체하고, 신규 3개를 추가한다.

```python
@pytest.mark.asyncio
async def test_collect_category_trends_merges_queries():
    # 쿼리마다 고유 link로 dedup 통과, AsyncMock으로 gather 호환
    async def fake_search(query, display=100, sort="sim"):
        return [{
            "title": "t", "description": "d",
            "link": f"https://blog.naver.com/{query}-{sort}",
            "postdate": "", "blogger_name": "", "blogger_link": "",
        }]

    with patch("app.ingestion.naver.search_naver_blog", side_effect=fake_search):
        result = await collect_category_trends("snack")

    queries = CATEGORY_KEYWORDS["snack"]
    assert len(result) == len(queries) * 2  # sim + date 각각 1개씩


@pytest.mark.asyncio
async def test_collect_category_trends_calls_both_sorts():
    called_sorts: list[str] = []

    async def fake_search(query, display=100, sort="sim"):
        called_sorts.append(sort)
        return [{
            "title": "t", "description": "d",
            "link": f"https://blog.naver.com/{query}-{sort}",
            "postdate": "", "blogger_name": "", "blogger_link": "",
        }]

    with patch("app.ingestion.naver.search_naver_blog", side_effect=fake_search):
        await collect_category_trends("snack")

    assert "sim" in called_sorts
    assert "date" in called_sorts


@pytest.mark.asyncio
async def test_collect_category_trends_deduplicates_by_link():
    dup_item = {
        "title": "t", "description": "d",
        "link": "https://blog.naver.com/same",
        "postdate": "", "blogger_name": "", "blogger_link": "",
    }

    with patch("app.ingestion.naver.search_naver_blog", new=AsyncMock(return_value=[dup_item])):
        result = await collect_category_trends("snack")

    # 동일 link는 1번만 남음
    assert len(result) == 1
    assert result[0]["link"] == "https://blog.naver.com/same"


@pytest.mark.asyncio
async def test_collect_category_trends_logs_warning_on_fetch_error(caplog):
    import logging

    async def failing_search(query, display=100, sort="sim"):
        raise RuntimeError("network error")

    with patch("app.ingestion.naver.search_naver_blog", side_effect=failing_search):
        with caplog.at_level(logging.WARNING, logger="app.ingestion.naver"):
            result = await collect_category_trends("snack")

    assert result == []
    assert any("naver blog fetch failed" in r.message for r in caplog.records)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/maknkkong/project/pet-data-api && ./venv/bin/pytest tests/test_naver_collector.py::test_collect_category_trends_merges_queries tests/test_naver_collector.py::test_collect_category_trends_calls_both_sorts tests/test_naver_collector.py::test_collect_category_trends_deduplicates_by_link tests/test_naver_collector.py::test_collect_category_trends_logs_warning_on_fetch_error -v
```

기대 결과: 4개 모두 `FAILED`.
- `merges_queries`: AsyncMock 미사용으로 gather에서 `TypeError` 또는 assertion 불일치
- `calls_both_sorts`: 현재 `sort="sim"` 고정이므로 `"date"` 미호출
- `deduplicates_by_link`: 중복 제거 로직 없으므로 len > 1
- `logs_warning`: logger 없음

- [ ] **Step 3: `collect_category_trends` 재작성**

`app/ingestion/naver.py` 상단 import 블록을 아래로 교체한다.

```python
import re
import asyncio
import logging
from app.platform.core.config import settings
from app.ingestion.client import fetch_public_api

logger = logging.getLogger(__name__)
```

`collect_category_trends` 함수를 아래로 교체한다.

```python
async def collect_category_trends(category: str) -> list[dict]:
    queries = CATEGORY_KEYWORDS.get(category, [])
    sem_limit = max(1, min(8, len(queries) * 2))
    semaphore = asyncio.Semaphore(sem_limit)

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

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
cd /Users/maknkkong/project/pet-data-api && ./venv/bin/pytest tests/test_naver_collector.py -v
```

기대 결과: 9개 모두 `PASSED`.

- [ ] **Step 5: 커밋**

```bash
cd /Users/maknkkong/project/pet-data-api && git add app/ingestion/naver.py tests/test_naver_collector.py && git commit -m "feat(naver): collect_category_trends gather+세마포어+link dedup 적용"
```

---

## 완료 기준 체크리스트

- [ ] `./venv/bin/pytest tests/test_naver_collector.py -v` → 9개 전부 PASSED
- [ ] `app/ingestion/naver.py`에 `import asyncio`, `import logging`, `logger = logging.getLogger(__name__)` 포함
- [ ] `search_naver_blog` 반환 dict에 `blogger_name`, `blogger_link` 키 존재
- [ ] `collect_category_trends` 내부에 `asyncio.Semaphore`, `asyncio.gather`, `seen: set[str]` 사용
- [ ] runner·trend analyzer 시그니처 변경 없음 (기존 `list[dict]` 반환 유지)
