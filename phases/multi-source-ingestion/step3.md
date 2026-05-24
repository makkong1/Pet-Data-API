# Step 3: 수집 레이어 병합 (블로그 + 카페 → PostRecord, link dedupe)

## 목표

`collect_category_trends()` 가 블로그·카페 양쪽을 수집해 `list[PostRecord]` 를 반환하도록 교체한다.
`extract_popular_names()` 도 카페 소스를 병렬로 추가해 상호명 집계 커버리지를 높인다.
인터페이스 변경에 맞춰 관련 테스트를 함께 수정한다.

> **주의**: `collect_category_trends` 반환 타입이 `list[dict]` → `list[PostRecord]` 로 바뀌므로
> `aggregate_keywords(items)` 호출부가 이 Step 직후에는 타입 불일치 상태가 된다.
> Step 4에서 `aggregate_keywords` 를 PostRecord 입력으로 교체하면 복원된다.

## 배경

Step 2에서 `search_naver_cafe()`, `_blog_items_to_records()`, `_cafe_items_to_records()` 가 같은
`naver.py` 에 추가됐다. 이 Step은 두 수집 함수가 두 소스를 통합해 단일 PostRecord 스트림으로
반환하도록 이어붙이는 배관 작업이다.

## 변경 파일

### `app/ingestion/naver.py` (수정 — `collect_category_trends` 함수 전체 교체)

기존 `collect_category_trends` 함수 전체를 아래로 **교체**한다 (함수 시그니처 포함):

```python
async def collect_category_trends(category: str) -> list:
    """블로그·카페 양쪽을 수집해 link dedupe → list[PostRecord] 반환."""
    queries = CATEGORY_KEYWORDS.get(category, [])
    if not queries:
        _log.warning(
            "naver collect_category_trends category=%s: no CATEGORY_KEYWORDS (empty queries)", category
        )
        return []

    semaphore = asyncio.Semaphore(_NAVER_SEM_LIMIT)

    async def _fetch_source(source: str, q: str, sort: str) -> list:
        async with semaphore:
            if source == "blog":
                items = await search_naver_blog(q, sort=sort)
                return _blog_items_to_records(items)
            items = await search_naver_cafe(q, sort=sort)
            return _cafe_items_to_records(items)

    tasks = [
        _fetch_source(src, q, s)
        for src in ("blog", "cafe")
        for q in queries
        for s in ("sim", "date")
    ]
    _log.info(
        "naver collect_category_trends start category=%r queries=%d parallel_calls=%d "
        "(blog+cafe×sim+date) sem_limit=%d",
        category, len(queries), len(tasks), _NAVER_SEM_LIMIT,
    )

    batches = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set[str] = set()
    results: list = []
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
        for r in batch:
            if not r.link:
                continue
            if r.link in seen:
                dup_skip += 1
                continue
            seen.add(r.link)
            results.append(r)

    _log.info(
        "naver collect_category_trends done category=%r unique_posts=%d raw_rows=%d "
        "dup_skip=%d parallel_ok=%d parallel_err=%d",
        category, len(results), raw_rows, dup_skip,
        len(tasks) - len(errs), len(errs),
    )
    if errs:
        _log.warning(
            "naver collect_category_trends category=%r error_samples(max3)=%s",
            category, errs[:3],
        )

    return results
```

### `app/ingestion/blog.py` (수정 2곳)

#### 수정 1 — import 변경

```python
# 변경 전
from app.ingestion.naver import CATEGORY_KEYWORDS, search_naver_blog
# 변경 후
from app.ingestion.naver import CATEGORY_KEYWORDS, search_naver_blog, search_naver_cafe
```

#### 수정 2 — `extract_popular_names` 수집 루프 교체

`all_items: list = []` 바로 다음 for 루프를 아래로 **교체**한다:

```python
    # 변경 전
    for query in queries:
        try:
            items = await search_naver_blog(query, display=100, sort="sim")
            all_items.extend(items)
        except Exception as exc:
            _log.warning("blog extract failed context=%s query=%r err=%s", normalized, query, exc)

    # 변경 후
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
```

### `tests/test_naver_collector.py` (수정 — 3개 테스트)

#### 수정 1 — `test_collect_category_trends_merges_queries` 전체 교체

```python
@pytest.mark.asyncio
async def test_collect_category_trends_merges_queries():
    async def fake_blog(query, display=100, sort="sim"):
        return [{
            "title": "t", "description": "d",
            "link": f"https://blog.naver.com/{query}-{sort}",
            "postdate": "", "blogger_name": "", "blogger_link": "",
        }]

    async def fake_cafe(query, display=100, sort="sim"):
        return [{
            "title": "t", "description": "d",
            "link": f"https://cafe.naver.com/{query}-{sort}",
            "postdate": "", "cafe_name": "", "cafe_link": "",
        }]

    with patch("app.ingestion.naver.search_naver_blog", side_effect=fake_blog), \
         patch("app.ingestion.naver.search_naver_cafe", side_effect=fake_cafe):
        result = await collect_category_trends("snack")

    queries = CATEGORY_KEYWORDS["snack"]
    # blog×(sim+date) + cafe×(sim+date) → queries * 4
    assert len(result) == len(queries) * 4
```

#### 수정 2 — `test_collect_category_trends_calls_both_sorts` 전체 교체

```python
@pytest.mark.asyncio
async def test_collect_category_trends_calls_both_sorts():
    called_sorts: list[str] = []

    async def fake_blog(query, display=100, sort="sim"):
        called_sorts.append(sort)
        return [{
            "title": "t", "description": "d",
            "link": f"https://blog.naver.com/{query}-{sort}",
            "postdate": "", "blogger_name": "", "blogger_link": "",
        }]

    async def fake_cafe(query, display=100, sort="sim"):
        return [{
            "title": "t", "description": "d",
            "link": f"https://cafe.naver.com/{query}-{sort}",
            "postdate": "", "cafe_name": "", "cafe_link": "",
        }]

    with patch("app.ingestion.naver.search_naver_blog", side_effect=fake_blog), \
         patch("app.ingestion.naver.search_naver_cafe", side_effect=fake_cafe):
        await collect_category_trends("snack")

    assert "sim" in called_sorts
    assert "date" in called_sorts
```

#### 수정 3 — `test_collect_category_trends_deduplicates_by_link` 전체 교체

```python
@pytest.mark.asyncio
async def test_collect_category_trends_deduplicates_by_link():
    dup_blog_item = {
        "title": "t", "description": "d",
        "link": "https://blog.naver.com/same",
        "postdate": "", "blogger_name": "", "blogger_link": "",
    }
    dup_cafe_item = {
        "title": "t", "description": "d",
        "link": "https://blog.naver.com/same",   # 블로그와 동일 link
        "postdate": "", "cafe_name": "", "cafe_link": "",
    }

    with patch("app.ingestion.naver.search_naver_blog", new=AsyncMock(return_value=[dup_blog_item])), \
         patch("app.ingestion.naver.search_naver_cafe", new=AsyncMock(return_value=[dup_cafe_item])):
        result = await collect_category_trends("snack")

    assert len(result) == 1
    assert result[0].link == "https://blog.naver.com/same"   # PostRecord 속성 접근
```

### `tests/test_blog.py` (수정 — 2개 테스트)

#### 수정 1 — `test_extract_popular_names_cross_query_link_dedupe`

`patch` 블록에 `search_naver_cafe` mock 추가:

```python
@pytest.mark.asyncio
async def test_extract_popular_names_cross_query_link_dedupe():
    """동일 link가 여러 쿼리에서 반환되어도 mention_count는 unique link 수만큼만 집계."""
    dup_post = {
        "title": "해피독 미용실 후기",
        "description": "해피독미용실 방문기",
        "link": "https://blog.naver.com/unique",
        "postdate": "20260501",
    }
    dup_post2 = {
        "title": "해피독 미용실 재방문",
        "description": "해피독미용실 두번째 방문기",
        "link": "https://blog.naver.com/unique2",
        "postdate": "20260501",
    }

    async def fake_search(query, display=100, sort="sim"):
        return [dup_post, dup_post2]

    with patch("app.ingestion.blog.search_naver_blog", side_effect=fake_search), \
         patch("app.ingestion.blog.search_naver_cafe", side_effect=fake_search):
        from app.ingestion.blog import extract_popular_names
        result = await extract_popular_names("grooming")

    해피독_entries = [r for r in result if r["name"] == "해피독"]
    assert 해피독_entries, "해피독 should be extracted from the grooming blog post"
    assert 해피독_entries[0]["mention_count"] == 2
```

#### 수정 2 — `test_collect_popular_for_context_aliases_supplies`

blog + cafe 양쪽 mock 추가, 호출 수 기댓값 업데이트:

```python
@pytest.mark.asyncio
async def test_collect_popular_for_context_aliases_supplies():
    """snack → supplies로 정규화된 쿼리셋을 사용."""
    called_queries: list = []

    async def fake_search(query, display=100, sort="sim"):
        called_queries.append(query)
        return []

    with patch("app.ingestion.blog.search_naver_blog", side_effect=fake_search), \
         patch("app.ingestion.blog.search_naver_cafe", side_effect=fake_search):
        from app.ingestion.blog import collect_popular_for_context
        await collect_popular_for_context("snack")

    from app.ingestion.naver import CATEGORY_KEYWORDS
    expected_queries = sum(len(CATEGORY_KEYWORDS[k]) for k in ("supplies", "snack", "food", "clothes"))
    # blog + cafe 각각 호출 → expected_queries * 2
    assert len(called_queries) == expected_queries * 2
```

## AC (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api && source venv/bin/activate

# 1. collect_category_trends → PostRecord 반환, 소스 두 종류 포함
python -c "
import asyncio
from unittest.mock import AsyncMock, patch

async def check():
    fake_blog = [{'title': '강아지 미용', 'description': '해피독 미용실',
                  'link': 'https://blog.naver.com/1', 'postdate': '20260501',
                  'blogger_name': '', 'blogger_link': ''}]
    fake_cafe = [{'title': '카페 포스트', 'description': '해피독 카페',
                  'link': 'https://cafe.naver.com/1', 'postdate': '20260501',
                  'cafe_name': '', 'cafe_link': ''}]
    with patch('app.ingestion.naver.search_naver_blog', new=AsyncMock(return_value=fake_blog)), \
         patch('app.ingestion.naver.search_naver_cafe', new=AsyncMock(return_value=fake_cafe)):
        from app.ingestion.naver import collect_category_trends
        from app.ingestion.record import PostRecord
        result = await collect_category_trends('grooming')
        assert all(isinstance(r, PostRecord) for r in result), 'must return PostRecord list'
        sources = {r.source for r in result}
        assert 'naver_blog' in sources and 'naver_cafe' in sources
        print('collect_category_trends ok, sources:', sources)

asyncio.run(check())
"

# 2. link dedupe — 블로그·카페가 같은 link 반환 시 1개로 합쳐짐
python -c "
import asyncio
from unittest.mock import AsyncMock, patch

async def check():
    same_link = 'https://blog.naver.com/shared'
    blog_item = {'title': 't', 'description': 'd', 'link': same_link,
                 'postdate': '', 'blogger_name': '', 'blogger_link': ''}
    cafe_item = {'title': 't', 'description': 'd', 'link': same_link,
                 'postdate': '', 'cafe_name': '', 'cafe_link': ''}
    with patch('app.ingestion.naver.search_naver_blog', new=AsyncMock(return_value=[blog_item])), \
         patch('app.ingestion.naver.search_naver_cafe', new=AsyncMock(return_value=[cafe_item])):
        from app.ingestion.naver import collect_category_trends
        result = await collect_category_trends('snack')
    assert len(result) == 1
    assert result[0].link == same_link
    print('dedupe ok')

asyncio.run(check())
"

# 3. 기존 테스트 통과
PYTHONPATH=. pytest tests/ -v
```
