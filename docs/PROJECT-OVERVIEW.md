# pet-data-api — 프로젝트 개요

이 문서는 **현재 저장소 코드**(`app/`, `migrations/`, `tests/`)를 기준으로, 이 프로젝트가 **무엇을 하고 어떻게 돌아가는지** 한곳에 정리한 것입니다. 세부 실행 절차는 [`USAGE.md`](USAGE.md), 엔드포인트 표는 루트 [`README.md`](../README.md)를 함께 보세요.

---

## 한 줄 요약

**data.go.kr 공공 API로 반려동물 영업장·동물병원 정보를 PostgreSQL에 적재하고**, **네이버 블로그 검색 + 형태소 분석으로 카테고리별 인기 키워드를 Redis에 캐시한 뒤**, **API Key 보호 REST API**로 시설·통계·트렌드를 제공하는 **FastAPI** 백엔드입니다.

---

## 역할과 경계

| 구분                              | 내용                                                                                                                                                                                                                                                  |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **데이터 적재 대상 (PostgreSQL)** | 행안부 공공데이터 기반 **반려동물 미용·판매 등 영업시설**(`petShop` 수집), **동물병원**(`animalHospital` 수집). 시설 공통 테이블 `pet_facilities`, 유형별 상세 `business_details` / `hospital_details`.                                               |
| **트렌드 (Redis)**                | 네이버 블로그 검색 결과 텍스트에서 **키워드 빈도**를 뽑아 **Sorted Set**으로 저장. API는 Redis에서만 읽음.                                                                                                                                            |
| **인증**                          | 모든 보호 엔드포인트는 **`X-API-Key`** 헤더. 서버에는 **SHA-256 해시**만 보관 (`API_KEY_HASH`, `ADMIN_API_KEY_HASH`). 관리자 전용(예: 수집 트리거)은 관리자 키만 허용.                                                                                |
| **DB 적용 순서**                  | [`migrations/init.sql`](../migrations/init.sql) 후 [`v2_pet_facilities.sql`](../migrations/v2_pet_facilities.sql) 필수. 이미 구 스키마가 있는 DB는 [`002_drop_abandoned_animals.sql`](../migrations/002_drop_abandoned_animals.sql) 등으로 정리 가능. |

---

## 런타임 동작 (사용자 요청)

1. **Uvicorn**으로 `app.main:app` 기동.
2. **Lifespan**에서 APScheduler가 시작되고, 프로세스 종료 시 스케줄러가 내려감.
3. 등록된 **HTTP 라우터**: `facilities`, `stats`, `collect`, `trends` (접두사·경로는 각 `app/api/*.py` 및 OpenAPI `/docs` 참고).
4. **DB 세션**은 `AsyncSessionLocal` + 의존성 주입으로 요청 단위 사용.
5. **트렌드 조회** (`GET /trends/{category}`)는 Redis에 연결해 키워드 순위와 갱신 시각을 반환. Redis 오류·데이터 없음 시 **503** 등으로 표현 (구현은 [`app/api/trends.py`](../app/api/trends.py)).

---

## 배치 동작 (스케줄)

설정 파일: [`app/scheduler/jobs.py`](../app/scheduler/jobs.py). 타임존을 별도 지정하지 않으므로 **프로세스 로컬 시각** 기준입니다.

| 시간 (cron)    | 잡 ID                    | 하는 일                                                                                                                                         |
| -------------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 매일 **18:00** | `daily_trend_collection` | `run_trend_collection`: 카테고리별 네이버 블로그 수집 → 형태소 분석으로 키워드 집계 → Redis `save_trend`. DB 세션을 쓰지 않는 독립 잡.          |
| 매일 **18:05** | `daily_collection`       | `run_collection`: 영업장 API → 추출·upsert, 동물병원 API → 추출·upsert. 각 소스마다 `collection_logs` 기록. `max_instances=1`로 중복 실행 방지. |

관리자 키로 **`POST /collect/trigger?scope=...`**를 호출하면 수동 수집 범위를 선택할 수 있습니다.

- `scope=facilities` (기본): 공공데이터 시설 수집
- `scope=trends`: 네이버 트렌드 수집
- `scope=all`: 트렌드 + 시설 수집

---

## 데이터 흐름 (개략)

```text
[data.go.kr]
    → app/collector/business.py · hospital.py (fetch + extract)
    → app/collector/runner.py::_upsert_facility
    → PostgreSQL (pet_facilities, *_details, collection_logs)

[네이버 블로그 Open API]
    → app/collector/naver.py
    → app/analyzer/trend.py (aggregate_keywords, kiwipiepy 기반)
    → app/cache/redis.py (Sorted Set)
    → GET /trends/{category} 가 Redis에서 조회
```

HTTP 클라이언트·재시도 등 공통은 [`app/collector/client.py`](../app/collector/client.py)를 따릅니다.

---

## 디렉터리 역할 (요약)

| 경로             | 역할                                                            |
| ---------------- | --------------------------------------------------------------- |
| `app/main.py`    | FastAPI 앱, 라우터 등록, lifespan에서 스케줄러 시작/종료        |
| `app/api/`       | `facilities`, `stats`, `collect`, `trends` 라우터               |
| `app/collector/` | 공공 API·네이버 수집, `run_collection` / `run_trend_collection` |
| `app/analyzer/`  | 형태소·트렌드 집계                                              |
| `app/cache/`     | Redis 트렌드 저장/조회                                          |
| `app/core/`      | 설정(`pydantic-settings`), 비동기 DB, API Key 검증              |
| `app/models/`    | ORM 모델(로그 등)                                               |
| `app/schemas/`   | Pydantic 응답 스키마                                            |
| `app/scheduler/` | APScheduler 잡 정의                                             |
| `migrations/`    | SQL 초기화·스키마 변경                                          |
| `tests/`         | API·수집기·분석기 테스트                                        |

---

## 트렌드 카테고리

[`app/collector/naver.py`](../app/collector/naver.py)의 `CATEGORY_KEYWORDS`와 동일해야 합니다: `supplies`, `snack`, `food`, `grooming`, `hospital`, `clothes`.

---

## 설계·계획 문서 (참고용)

- [`superpowers/specs/2026-04-19-pet-data-api-design.md`](superpowers/specs/2026-04-19-pet-data-api-design.md) — 초기 설계 맥락
- [`superpowers/specs/2026-04-21-pet-trend-pipeline-design.md`](superpowers/specs/2026-04-21-pet-trend-pipeline-design.md) — 트렌드 파이프라인
- [`superpowers/specs/2026-05-01-petory-category-recommendation-redesign.md`](superpowers/specs/2026-05-01-petory-category-recommendation-redesign.md) — Petory 카테고리 추천 재설계안
- [`superpowers/plans/2026-04-21-pet-trend-pipeline.md`](superpowers/plans/2026-04-21-pet-trend-pipeline.md) — 구현 플랜(체크리스트)
- [`superpowers/plans/2026-05-02-phase1-refactor-log.md`](superpowers/plans/2026-05-02-phase1-refactor-log.md) — 1차 리팩토링 반영 로그

---

## 진행 상황을 코드로 읽는 법

- **마이그레이션 파일 목록**과 `git log`로 스키마 변천을 추적할 수 있습니다.
- **`phases/index.json`**은 현재 비어 있으며, 단계 관리용 자리 표시자로 두었을 수 있습니다. 실행·배포 절차는 본 문서와 `USAGE.md`를 따르면 됩니다.

문제가 나면 **`DATABASE_URL`**, **해시·서비스키·네이버 키**, **Redis 가용성**, **`psql`로 `pet_facilities` 등 테이블 존재**를 순서대로 확인하는 것이 빠릅니다.
