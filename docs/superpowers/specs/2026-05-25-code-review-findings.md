# 코드 리뷰 결과 — pet-data-api

> 리뷰 일자: 2026-05-25 / 브랜치: dev / 리뷰어: Claude Sonnet 4.6
>
> 범위: `app/` 전체 (`serving/`, `ingestion/`, `platform/`)  
> 컨텍스트: Petory recommendation 백엔드 도메인과의 연동 품질 포함

---

## 요약 점수판

| 카테고리 | Critical | Warning | Info |
|---------|----------|---------|------|
| 쿼리/페이징 | 1 | 0 | 0 |
| 트랜잭션/스케줄 | 0 | 1 | 0 |
| 보안 | 0 | 0 | 0 |
| FastAPI | 0 | 1 | 1 |
| 코드품질 | 0 | 2 | 2 |
| **합계** | **1** | **4** | **3** |

→ **🔴 수정 필요** (Critical 1개 해소 전까지 프로덕션 배포 주의)

---

## 🔴 Critical

### [C-1] `/facilities` — offset 기반 페이징, cursor 네이밍 오류

**파일**: `app/serving/api/facilities.py:122-141`

**문제**

`cursor` 파라미터가 실제로는 배열 index(offset)다.

```python
# 현재 코드
page = all_items[cursor: cursor + limit]          # offset slice
next_cursor = cursor + limit if cursor + limit < total else None
```

- 응답 필드명이 `next_cursor`이지만 의미는 "다음 시작 offset"
- 두 요청 사이에 popular 배치가 실행되면 같은 cursor 값으로 다른 결과가 나올 수 있음 (phantom read / skip)
- Petory `FacilitySyncService`가 01:00 daily로 전체 목록을 당겨갈 때, 배치 시각(18:10)과 겹치지 않으면 실질적 문제는 없지만 인터페이스 계약이 틀림

**원인**

`_load_all_facilities()`가 매 요청마다 9개 Redis key를 전부 읽어 Python 리스트를 만든 뒤 slice한다. 키 순서 기반 cursor가 없어서 정수 offset으로 대체된 상태.

**개선 방향**

```python
# Option A (최소 변경): 파라미터를 솔직하게 offset으로 명명하고 문서화
cursor: int = Query(0, ge=0, description="페이징 오프셋 (0부터 시작)")
```

```python
# Option B (권장, 안정적): 배치 완료 후 집계 결과를 Redis 스냅샷 키로 저장
# popular 배치 완료 → RENAME facilities:staging → facilities:snapshot
# GET /facilities → redis.get("facilities:snapshot") → cursor는 진짜 offset-safe
```

Option B는 배치 원자성 보장 + read 성능 개선(9→1 Redis call)까지 함께 해결된다.

---

## 🟡 Warning

### [W-1] `GET /trends/{category}` — `response_model` 누락

**파일**: `app/serving/api/trends.py:16`

**문제**

`@router.get("/{category}")` 에 `response_model` 미선언. Swagger schema에 응답 타입이 `Any`로 노출되며, Petory 클라이언트 OpenAPI codegen 시 타입 안전성 없음.

**개선 코드**

```python
# app/serving/api/trends.py 상단에 추가
from pydantic import BaseModel
from typing import Optional

class TrendKeyword(BaseModel):
    keyword: str
    score: int

class TrendResponse(BaseModel):
    category: str
    updated_at: Optional[str]
    keywords: list[TrendKeyword]

# 라우터 데코레이터
@router.get("/{category}", response_model=TrendResponse)
```

---

### [W-2] `_load_all_facilities()` — 매 요청마다 full Redis scan

**파일**: `app/serving/api/facilities.py:60-109`

**문제**

`GET /facilities` 요청마다 9번 `r.get()` + `json.loads()` + Python 루프 전체가 실행된다. Petory 동기화가 짧은 간격으로 여러 번 호출하거나 부하 테스트 시 불필요한 Redis/CPU 소모.

**개선 방향**

[C-1]의 Option B(배치 완료 후 스냅샷 키)를 구현하면 자동 해소된다.  
단기 패치가 필요하다면 `functools.lru_cache` 또는 짧은 TTL 인메모리 캐시(30s)를 `_load_all_facilities` 에 추가.

---

### [W-3] APScheduler 타임존 미지정

**파일**: `app/platform/scheduler/jobs.py:8-16`

**문제**

```python
scheduler.add_job(run_trend_collection, trigger="cron", hour=18, minute=0, ...)
```

`timezone` 파라미터 없음. Docker/클라우드 컨테이너 TZ가 UTC이면 KST 18:00 대신 UTC 18:00 (KST 03:00)에 실행됨.

**개선 코드**

```python
from zoneinfo import ZoneInfo

scheduler.add_job(
    run_trend_collection,
    trigger="cron",
    hour=18, minute=0,
    timezone=ZoneInfo("Asia/Seoul"),   # 추가
    max_instances=1,
    id="daily_trend_collection",
)
```

Python 3.9+ 표준 라이브러리 `zoneinfo` 사용. `pytz` 추가 설치 불필요.

---

### [W-4] `save_posts()` — 삽입 건수 오보

**파일**: `app/platform/store/sqlite.py:71-78`

**문제**

`INSERT OR IGNORE` 를 사용하면서 `inserted = len(rows)` 를 반환해 로그에 "inserted N rows"로 찍힌다. 중복 링크는 skip되므로 실제 insert 수와 다를 수 있다.

**개선 코드**

```python
async with aiosqlite.connect(path) as db:
    await db.executemany(INSERT_OR_IGNORE_SQL, rows)
    await db.commit()
    inserted = db.total_changes   # 실제 변경 건수
```

---

## ℹ️ Info

### [I-1] `FacilityItem` 에서 `score`, `mention_count` 누락 — Petory 추천 신호 손실

**파일**: `app/serving/api/facilities.py:60-109` / `app/platform/schemas/popular.py`

**문제**

`PopularEntry`에는 `score: float`, `mention_count: int`가 있으나 `_load_all_facilities()`에서 `FacilityItem`으로 변환할 때 두 필드를 버린다. Petory `RecommendService`의 `popularityScore` 가중치(현재 0.10)는 `GET /popular/{context}` 에서 별도로 불러오는 구조이나, `/facilities` sync 경로를 통해 DB에 인기도 점수를 함께 적재하면 위치 기반 검색 후 추가 API 호출 없이 랭킹 가능.

**개선 방향**

```python
# app/serving/api/facilities.py — FacilityItem 모델
class FacilityItem(BaseModel):
    ...
    popularity_score: Optional[float] = None   # PopularEntry.score
    mention_count: Optional[int] = None        # PopularEntry.mention_count
```

```python
# _load_all_facilities() 내 변환 시
items.append(FacilityItem(
    ...
    popularity_score=entry.get("score"),
    mention_count=entry.get("mention_count"),
))
```

---

### [I-2] `POST /collect/trigger?wait=true` — 요청 레벨 타임아웃 없음

**파일**: `app/serving/api/collect.py:138-173`

**문제**

`wait=true` 모드에서 `asyncio.gather(run_popular_collection(), run_trend_collection())`를 같은 HTTP 요청 안에서 실행. 각 runner가 네이버 API를 수십 회 호출하므로 수 분 소요 가능. 클라이언트/프록시 타임아웃으로 연결이 먼저 끊겨도 서버는 계속 실행됨.

**개선 방향**

`wait=true`는 로컬 개발 편의용으로만 사용하도록 Swagger description에 명시 (현재 이미 일부 언급됨). 운영 환경에서는 `wait=false`(BackgroundTasks) 또는 별도 스케줄러 경로를 사용.  
필요 시 `asyncio.wait_for(..., timeout=300)` 으로 5분 하드 컷.

---

### [I-3] `trigger_collection()` 함수 길이

**파일**: `app/serving/api/collect.py:95-192` (약 98줄)

`wait=True` / `wait=False` 두 분기를 한 함수에서 처리. 가독성 저하.

```python
# 개선 방향: 분리
async def _handle_sync(dedup, rid, request) -> CollectTriggerResponse: ...
async def _handle_async(dedup, rid, background_tasks, request) -> CollectTriggerResponse: ...

async def trigger_collection(...):
    ...
    if wait:
        return await _handle_sync(dedup, rid, request)
    return await _handle_async(dedup, rid, background_tasks, request)
```

---

## ✅ 잘된 점

- **보안 전반 Clean**: `require_api_key` / `require_admin_key` 모든 엔드포인트 적용, SHA-256 비교, 평문 해시 오전송 감지 로직까지 갖춤.
- **Redis pipeline 사용**: `save_trend()`에서 `async with r.pipeline()`으로 delete/zadd/setex/expire 원자적 처리.
- **관측성**: `request_id` 미들웨어 + `integration_trace`로 인바운드/아웃바운드 구조화 로그.
- **인증 에러 UX**: 헤더에 hash를 평문으로 넣었을 때 힌트 메시지 제공, 401 vs 403 구분 명확.
- **Naver 외부 호출 제어**: semaphore + 지수 백오프 재시도(1s/2s/4s).
- `.env` gitignore 포함 확인.

---

## Petory recommendation 도메인 관점

| 항목 | 현재 상태 | 권고 |
|------|----------|------|
| 인기도 신호 전달 | `FacilityItem`에서 `score`/`mention_count` 드롭 | [I-1] 참고 — 두 필드 살려서 Petory가 랭킹에 활용 |
| 동기화 일관성 | 배치 중 `/facilities` 호출 시 half-written 상태 가능 | [C-1] Option B — 배치 완료 후 atomic rename |
| 페이징 안정성 | offset 기반 — 배치 실행 중 페이지 결과 변동 가능 | [C-1] 참고 |
| 데이터 신선도 | TTL 25h, 배치 24h 주기 — 최대 1시간 공백 가능 | Petory 측 stale 데이터 대응 로직 필요 |
| 위치 좌표 형식 | `map_x/map_y`는 Naver 형식(×10⁷ 정수 문자열), `/facilities`에서 float 변환 | `PopularEntry` 저장 시점에도 변환 통일 권장 |

---

## 우선순위 권장 순서

| 순서 | 이슈 | 이유 |
|------|------|------|
| 1 | [C-1] facilities 스냅샷 키 도입 | pagination 안정성 + Redis call 9→1 + Petory sync 신뢰성 |
| 2 | [W-3] APScheduler timezone | 배포 환경에서 배치 시각 오류 — 운영 전 필수 |
| 3 | [W-1] TrendResponse response_model | Petory codegen 타입 안전성 |
| 4 | [I-1] FacilityItem popularity_score | Petory 추천 품질 개선 |
| 5 | [W-4] save_posts count | 로그 정확도 |
| 6 | [W-2] load_all_facilities 캐시 | [C-1] 해결 시 자동 해소 |
