# Step 4: runner.py SQLite 저장 연결 + 분석 파이프 PostRecord 입력 지원

## 목표

`aggregate_keywords()` 가 `list[PostRecord]` 를 직접 받도록 교체하고,
`run_trend_collection()` 에서 수집된 PostRecord 목록을 SQLite `raw_posts` 에 저장한다.
이 Step을 완료하면 트렌드 파이프 전체(수집 → 저장 → 집계 → Redis)가 멀티소스 PostRecord 기반으로 통합된다.

## 배경

Step 3에서 `collect_category_trends()` 가 `list[PostRecord]` 를 반환하도록 바뀌었다.
Step 1에서 `save_posts()` 와 `init_db()` 가 추가됐다.
이 Step은 두 변경을 runner.py 에서 이어붙이고, 분석 파이프도 PostRecord 필드를 직접 읽도록 갱신한다.

> **범위 외**: `extract_popular_names()` 는 집계 점수를 반환하고 raw PostRecord 를 노출하지 않으므로
> 인기 파이프의 SQLite 저장은 이 Step 에 포함하지 않는다.

## 변경 파일

### `app/ingestion/analyzer/trend.py` (수정 — `aggregate_keywords` 함수 전체 교체)

```python
from collections import Counter
from app.ingestion.analyzer.morpheme import extract_nouns


def aggregate_keywords(items: list) -> Counter:
    """list[PostRecord] → 키워드 빈도 Counter."""
    counter: Counter = Counter()
    for r in items:
        text = f"{r.title} {r.description}"
        counter.update(extract_nouns(text))
    return counter
```

### `app/ingestion/runner.py` (수정 — import 추가·`run_trend_collection` 수정)

#### 수정 1 — import 추가

파일 상단 import 블록에 두 줄 추가:

```python
from datetime import datetime, timezone
from app.platform.store.sqlite import init_db, save_posts
```

#### 수정 2 — `run_trend_collection` 함수 전체 교체

```python
async def run_trend_collection() -> list[dict]:
    await init_db()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    collected_at = datetime.now(timezone.utc).isoformat()

    results = []
    ok = failed = skipped = 0
    for category in CATEGORY_KEYWORDS:
        try:
            items = await collect_category_trends(category)
            await save_posts(
                items,
                run_id=run_id,
                pipeline="trends",
                category=category,
                query=category,
                collected_at=collected_at,
            )
            counts = aggregate_keywords(items)
            if not counts:
                idlog.log_trend_skipped(
                    category,
                    blog_items=len(items),
                    reason="empty_counter_after_aggregate",
                )
                results.append(
                    {"category": category, "status": "skipped_empty", "keywords_count": 0}
                )
                skipped += 1
                continue
            await save_trend(category, dict(counts))
            idlog.log_trend_stored(
                category,
                blog_items=len(items),
                term_count=len(counts),
                counts=counts,
            )
            results.append({"category": category, "status": "success", "keywords_count": len(counts)})
            ok += 1
        except Exception as e:
            failed += 1
            _log.error("trend collection failed category=%s err=%s", category, e)
            results.append({"category": category, "status": "failed", "error_message": str(e)})

    idlog.log_batch_summary(
        "run_trend_collection", ok=ok, failed=failed, skipped=skipped, detail=results
    )
    return results
```

### `tests/test_analyzer.py` (수정 — PostRecord 입력으로 전환)

`test_aggregate_keywords_counts_frequency` 와 `test_aggregate_keywords_empty_input` 두 함수를 교체:

```python
def test_aggregate_keywords_counts_frequency():
    from app.ingestion.record import PostRecord
    items = [
        PostRecord(title="오리젠 간식 후기", description="오리젠 추천",
                   link="http://a", postdate="20260101", source="naver_blog"),
        PostRecord(title="로얄캐닌 사료", description="오리젠 비교",
                   link="http://b", postdate="20260101", source="naver_blog"),
    ]
    counter = aggregate_keywords(items)
    assert isinstance(counter, Counter)
    assert counter["오리젠"] >= 2


def test_aggregate_keywords_empty_input():
    counter = aggregate_keywords([])
    assert len(counter) == 0
```

## AC (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api && source venv/bin/activate

# 1. aggregate_keywords PostRecord 입력 확인
python -c "
from app.ingestion.record import PostRecord
from app.ingestion.analyzer.trend import aggregate_keywords
items = [
    PostRecord(title='오리젠 간식 후기', description='오리젠 추천',
               link='http://a', postdate='20260101', source='naver_blog'),
    PostRecord(title='로얄캐닌 사료', description='오리젠 비교',
               link='http://b', postdate='20260101', source='naver_blog'),
]
c = aggregate_keywords(items)
assert c['오리젠'] >= 2
print('aggregate_keywords ok, 오리젠 count:', c['오리젠'])
"

# 2. run_trend_collection → SQLite 저장 확인 (실제 API 호출 없이)
python -c "
import asyncio
from unittest.mock import AsyncMock, patch
from app.ingestion.record import PostRecord

fake_post = PostRecord(title='해피독 미용', description='미용 후기',
                       link='http://blog/1', postdate='20260501', source='naver_blog')

async def check():
    with patch('app.ingestion.runner.collect_category_trends', new=AsyncMock(return_value=[fake_post])), \
         patch('app.ingestion.runner.aggregate_keywords', return_value={'미용': 3}), \
         patch('app.ingestion.runner.save_trend', new=AsyncMock()), \
         patch('app.ingestion.runner.init_db', new=AsyncMock()), \
         patch('app.ingestion.runner.save_posts', new=AsyncMock(return_value=1)) as mock_save:
        from app.ingestion.runner import run_trend_collection
        results = await run_trend_collection()
    assert mock_save.called, 'save_posts must be called'
    assert any(r['status'] == 'success' for r in results)
    print('run_trend_collection ok, save_posts called:', mock_save.call_count, 'times')

asyncio.run(check())
"

# 3. 전체 파이프라인 통합 확인 (SQLite 실 기록)
python -c "
import asyncio, sqlite3
from unittest.mock import AsyncMock, patch
from app.ingestion.record import PostRecord
from app.platform.core.config import settings

fake_posts = [
    PostRecord(title='오리젠 후기', description='간식 추천', link='http://a',
               postdate='20260101', source='naver_blog'),
    PostRecord(title='카페 후기', description='간식 비교', link='http://b',
               postdate='20260101', source='naver_cafe'),
]

async def check():
    with patch('app.ingestion.runner.collect_category_trends', new=AsyncMock(return_value=fake_posts)), \
         patch('app.ingestion.runner.save_trend', new=AsyncMock()):
        from app.ingestion.runner import run_trend_collection
        await run_trend_collection()

    con = sqlite3.connect(settings.SQLITE_PATH)
    rows = con.execute(
        \"SELECT source, COUNT(*) FROM raw_posts WHERE pipeline='trends' GROUP BY source\"
    ).fetchall()
    con.close()
    print('sqlite rows by source:', rows)
    sources = {r[0] for r in rows}
    assert 'naver_blog' in sources
    assert 'naver_cafe' in sources
    print('sqlite ok')

asyncio.run(check())
"

# 4. 기존 테스트 통과
PYTHONPATH=. pytest tests/ -v
```
