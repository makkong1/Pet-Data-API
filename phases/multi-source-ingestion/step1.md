# Step 1: PostRecord 정규화 모델 + SQLite raw_posts 테이블 구축

## 목표

블로그·카페 등 소스가 달라도 동일한 내부 표현으로 다룰 수 있는 `PostRecord` 데이터 모델을 만들고,
원본 포스트를 영속 보관할 SQLite `raw_posts` 테이블과 비동기 저장 함수를 구축한다.
이 Step에서는 API 호출이나 기존 파이프 변경 없이 **기반 레이어만** 완성한다.

## 배경

현재 `search_naver_blog()` → `list[dict]` 형태로 데이터가 흐르며 소스 구분이 없다.
카페를 추가할 때 `bloggername`과 `cafeName` 같은 소스별 필드 차이를 흡수하는 정규화 모델이 없으면
이후 병합·dedupe·분석 레이어가 소스에 종속된다.

SQLite는 Python 표준 라이브러리 `sqlite3` 기반이며 `aiosqlite` 래퍼로 async 환경에서 사용한다.
별도 서버 없이 `data/raw_posts.db` 파일 하나로 동작한다.

## 변경 파일

### 1. `requirements.txt` (수정)

`aiosqlite>=0.20` 한 줄 추가. 위치는 기존 의존성 블록 끝.

```
aiosqlite>=0.20
```

### 2. `app/platform/core/config.py` (수정)

`Settings` 클래스에 `SQLITE_PATH` 필드 추가:

```python
SQLITE_PATH: str = "data/raw_posts.db"
```

`.env.example`에도 주석으로 추가:

```
# SQLite 원본 포스트 저장 경로 (기본값: data/raw_posts.db)
# SQLITE_PATH=data/raw_posts.db
```

### 3. `app/ingestion/record.py` (신규)

소스 무관 내부 포스트 표현. dataclass로 작성한다.

```python
from dataclasses import dataclass, field


@dataclass
class PostRecord:
    title:       str
    description: str
    link:        str        # 전역 dedupe 키
    postdate:    str        # "YYYYMMDD" 또는 빈 문자열
    source:      str        # "naver_blog" | "naver_cafe"
    author_name: str = field(default="")   # bloggername or cafeName
    author_link: str = field(default="")   # bloggerlink or cafeLink

    def to_dict(self) -> dict:
        """기존 list[dict] 기반 분석 함수(aggregate_keywords 등)와 호환."""
        return {
            "title":        self.title,
            "description":  self.description,
            "link":         self.link,
            "postdate":     self.postdate,
            "blogger_name": self.author_name,
            "blogger_link": self.author_link,
        }
```

### 4. `app/platform/store/sqlite.py` (신규)

SQLite 연결·테이블 생성·배치 저장 함수.

```python
import aiosqlite
import logging
from pathlib import Path
from app.platform.core.config import settings

_log = logging.getLogger(__name__)


async def init_db() -> None:
    """앱 시작 또는 배치 시작 시 한 번 호출. 테이블이 없으면 생성한다."""
    path = Path(settings.SQLITE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS raw_posts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       TEXT    NOT NULL,
                source       TEXT    NOT NULL,
                pipeline     TEXT    NOT NULL,
                category     TEXT    NOT NULL,
                query        TEXT    NOT NULL,
                link         TEXT    NOT NULL,
                title        TEXT,
                description  TEXT,
                postdate     TEXT,
                author_name  TEXT,
                collected_at TEXT    NOT NULL,
                UNIQUE(link)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_rp_run    ON raw_posts(run_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_rp_source ON raw_posts(source, pipeline, category)"
        )
        await db.commit()
    _log.info("sqlite init_db ok path=%s", path)


async def save_posts(
    records: list,          # list[PostRecord]
    run_id: str,
    pipeline: str,          # "trends" | "popular"
    category: str,
    query: str,
    collected_at: str,      # ISO 8601
) -> int:
    """PostRecord 리스트를 raw_posts 에 삽입. UNIQUE(link) 충돌은 무시(OR IGNORE)."""
    if not records:
        return 0

    rows = [
        (
            run_id, r.source, pipeline, category, query,
            r.link, r.title, r.description, r.postdate,
            r.author_name, collected_at,
        )
        for r in records
    ]
    path = Path(settings.SQLITE_PATH)
    async with aiosqlite.connect(path) as db:
        await db.executemany(
            """
            INSERT OR IGNORE INTO raw_posts
                (run_id, source, pipeline, category, query, link,
                 title, description, postdate, author_name, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        await db.commit()
    inserted = len(rows)
    _log.info(
        "sqlite save_posts pipeline=%s category=%s source_sample=%s rows=%d",
        pipeline, category,
        records[0].source if records else "-",
        inserted,
    )
    return inserted
```

## AC (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api && source venv/bin/activate

# 1. aiosqlite 설치 확인
pip install -r requirements.txt
python -c "import aiosqlite; print('aiosqlite ok')"

# 2. PostRecord 생성·to_dict 확인
python -c "
from app.ingestion.record import PostRecord
r = PostRecord(title='테스트', description='설명', link='http://a.com',
               postdate='20250524', source='naver_blog',
               author_name='블로거', author_link='http://b.com')
d = r.to_dict()
assert d['title'] == '테스트'
assert d['blogger_name'] == '블로거'
print('PostRecord ok', d)
"

# 3. SQLite 테이블 생성 확인
python -c "
import asyncio
from app.platform.store.sqlite import init_db
asyncio.run(init_db())
import sqlite3, os
from app.platform.core.config import settings
con = sqlite3.connect(settings.SQLITE_PATH)
tables = con.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print('tables:', tables)
con.close()
"

# 4. pytest (기존 테스트 깨지지 않는지)
PYTHONPATH=. pytest tests/ -v
```
