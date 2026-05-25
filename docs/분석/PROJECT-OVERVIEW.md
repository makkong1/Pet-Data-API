# pet-data-api — 프로젝트 개요

> 코드 기준: dev 브랜치 2026-05-25

## 한 줄 정의

네이버 블로그·카페 검색으로 반려동물 서비스 **트렌드 키워드**와 **컨텍스트별 인기 상호**를 수집·집계하여 Redis에 두고, REST API로 노출하는 Python/FastAPI 서비스.  
Petory(Java/Spring)와 별개 레포로 운영되며, Petory의 `FacilitySyncService`·`PetDataApiClient`가 이 서비스를 소비한다.

이 레포에 없는 것: PostgreSQL, Kakao 지오코더, Ollama/LLM, 추천 엔진, 행안부 공공데이터 적재.

---

## API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/healthz` | Liveness probe — 항상 200 | 없음 |
| GET | `/readyz` | Redis ping readiness — Redis 오류 시 503 | 없음 |
| GET | `/metrics` | Prometheus (prometheus-fastapi-instrumentator 설치 시) | 없음 |
| GET | `/trends/{category}` | 카테고리별 트렌드 키워드 순위 (Sorted Set) | 일반 키 |
| GET | `/popular/{context}` | 컨텍스트별 인기 상호 목록 (최대 20) | 일반 키 |
| GET | `/facilities` | cursor 기반 시설 목록 (FacilitySyncService 연동용) | 일반 키 |
| POST | `/collect/trigger` | 배치 수동 실행 (`{"targets":["popular","trends"]}`) | 관리자 키 |

인증: `X-API-Key` 헤더 평문의 SHA-256이 `.env`의 `API_KEY_HASH`(일반) 또는 `ADMIN_API_KEY_HASH`(관리자)와 일치해야 함.

---

## 컨텍스트·카테고리 목록

**트렌드 카테고리 (12개)** — `CATEGORY_KEYWORDS` in `app/ingestion/naver.py`

`supplies` `snack` `food` `grooming` `hospital` `clothes` `pharmacy` `cafe` `pension` `restaurant` `boarding` `hotel`

**인기 컨텍스트 (9개)** — `_POPULAR_CONTEXTS` in `app/ingestion/runner.py`

`grooming` `hospital` `supplies` `pharmacy` `cafe` `pension` `restaurant` `boarding` `hotel`

**인기 컨텍스트 별칭** (API 레벨에서 정규화)

`snack` → `supplies` / `food` → `supplies` / `clothes` → `supplies`

---

## 배치 파이프라인

### 트렌드 (매일 18:00)

`naver.CATEGORY_KEYWORDS` 12개 카테고리 × 쿼리목록 → 블로그+카페 API 호출 (sim+date 이중)  
→ `analyzer/trend.aggregate_keywords()` kiwipiepy 형태소(NNG/NNP) + STOPWORDS 필터  
→ Redis `trends:{category}:keywords` Sorted Set (TTL 24h)

### 인기 상호 (매일 18:10)

- **boarding, hotel** — `local_discovery.collect_popular_local_discovery(context)`:  
  Naver Local API로 후보 발견 → 블로그 언급으로 검증 → 위치정보 포함 상태로 저장
- **나머지 7개 context** — `blog.collect_popular_for_context(context)`:  
  블로그/카페 API → regex 상호명 추출 → freshness 스코어링  
  → `location.enrich_with_location()` Naver Local로 address/map_x/map_y/telephone 보강  
→ Redis `popular:{context}` JSON (TTL 25h)

### 스케줄러

`app/platform/scheduler/jobs.py` — APScheduler `max_instances=1`

| 작업 | cron |
|------|------|
| 트렌드 | 매일 18:00 (로컬) |
| 인기 | 매일 18:10 (로컬) |

---

## Redis 키 설계

| 키 | 타입 | TTL | 내용 |
|----|------|-----|------|
| `trends:{category}:keywords` | Sorted Set | 24h | keyword → mention_count |
| `trends:{category}:updated_at` | String | 24h | ISO 8601 갱신 시각 |
| `popular:{context}` | String (JSON) | 25h | `[{name, mention_count, avg_freshness, score, address?, road_address?, map_x?, map_y?, telephone?}]` |

`GET /facilities`는 `popular:*` 전체 키를 스캔하여 `address` 있는 항목만 FacilityItem으로 변환해 반환.

---

## 환경변수 (`.env`)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `API_KEY_HASH` | 필수 | 일반 API 키 SHA-256 hex (64자) |
| `ADMIN_API_KEY_HASH` | 필수 | 관리자 키 SHA-256 hex (64자) |
| `NAVER_CLIENT_ID` | 필수 | 네이버 Open API Client ID |
| `NAVER_CLIENT_SECRET` | 필수 | 네이버 Open API Client Secret |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 연결 URL |
| `NAVER_TIMEOUT_MS` | `10000` | 네이버 API 타임아웃 (ms) |
| `SQLITE_PATH` | `data/raw_posts.db` | 원시 포스트 로컬 저장 경로 |

키 해시 생성:
```bash
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print(k, hashlib.sha256(k.encode()).hexdigest())"
```

---

## 프로젝트 구조

```
pet-data-api/
├── app/
│   ├── main.py                    # FastAPI app, lifespan, 라우터 등록
│   ├── ingestion/
│   │   ├── naver.py               # Naver API 호출, CATEGORY_KEYWORDS
│   │   ├── blog.py                # 인기 상호 추출·스코어링 (7개 context)
│   │   ├── local_discovery.py     # boarding/hotel Local→Blog 2단계 파이프라인
│   │   ├── location.py            # Naver Local로 address/좌표 보강
│   │   ├── runner.py              # 배치 진입점 (run_trend/popular_collection)
│   │   └── analyzer/
│   │       ├── trend.py           # aggregate_keywords (Counter)
│   │       └── morpheme.py        # kiwipiepy + STOPWORDS
│   ├── serving/api/
│   │   ├── trends.py              # GET /trends/{category}
│   │   ├── popular.py             # GET /popular/{context}
│   │   ├── facilities.py          # GET /facilities (cursor 페이징)
│   │   └── collect.py             # POST /collect/trigger
│   └── platform/
│       ├── core/config.py         # pydantic-settings, .env 로드
│       ├── core/auth.py           # require_api_key / require_admin_key
│       ├── cache/redis.py         # get_redis, save_trend, get_trend, Redis 키 상수
│       ├── scheduler/jobs.py      # APScheduler 등록
│       ├── schemas/               # Pydantic 스키마
│       └── observability.py       # /healthz /readyz /metrics, AccessLogMiddleware
├── tests/
├── docs/분析/                     # 현재 기준 아키텍처·설계 문서
└── phases/                        # Harness 태스크 정의
```

---

## 실행

```bash
source venv/bin/activate
pip install -r requirements.txt
# Redis 준비 + .env 작성 후
uvicorn app.main:app --reload

# 테스트
PYTHONPATH=. pytest tests/ -v
```

Swagger UI: `http://localhost:8000/docs`

---

## Petory 연동 구조

```
Petory FacilitySyncScheduler (01:00 daily)
  → GET /facilities?cursor=0&limit=100
  → LocationService DB 적재 (dataSource=PET_DATA_API)

Petory RecommendService (사용자 요청)
  Track A (grooming/hospital/pharmacy/cafe/restaurant/pension/boarding/hotel)
    → Petory DB 반경 검색 (nearby 후보)
    → GET /popular/{context}   (blog signal)
    → GET /trends/{category}   (trend signal)
    → 조합·정렬·응답 조립
  Track B (supplies/snack/food/clothes)
    → PetDataApiClient.recommend() 레거시 경로 유지
```

---

## 관련 문서

| 문서 | 위치 |
|------|------|
| 데이터·API 흐름도 | [`DATA-AND-API-FLOW.md`](DATA-AND-API-FLOW.md) |
| 아키텍처 상세 | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Petory 연동 가이드 | [`PETORY-INTEGRATION.md`](PETORY-INTEGRATION.md) |
| Petory↔pet-data-api 재설계 분석 | [`04-petory-nearby-signal-architecture-redesign.md`](04-petory-nearby-signal-architecture-redesign.md) |
| 설계 근거(SSOT) | [`../superpowers/specs/2026-05-23-popularity-intelligence-redesign.md`](../superpowers/specs/2026-05-23-popularity-intelligence-redesign.md) |
