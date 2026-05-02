# pet-data-api

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-llama3-000000)

> 공공데이터 + 네이버 블로그 트렌드 + Ollama LLM 기반 반려동물 추천·시설·트렌드 REST API

---

## 프로젝트 소개

반려동물 생활 정보를 **세 가지 신호**로 엮어 한 번에 제공하는 Python 백엔드입니다.

- **공공데이터 (행안부)** — 전국 동물미용업·동물병원 공식 등록 정보를 수집해 `pet_facilities` 테이블에 적재. 주소는 **Kakao 로컬 API**로 지오코딩해 `lat/lng` 컬럼에 저장.
- **네이버 블로그 API + 형태소 분석(kiwipiepy)** — 간식·사료·미용·병원·옷 카테고리별 블로그 텍스트에서 키워드를 뽑아 Redis Sorted Set에 일일 갱신.
- **Ollama llama3 (로컬 LLM)** — 사용자의 GPS·반려동물 정보·반경 내 공인 시설·트렌드 키워드를 묶어 한 문단 추천을 생성.

Java/Spring 기반 [Petory](https://github.com/makkong1/Petory)에서 **`POST /recommend`를 호출**해 현재 페이지 맥락(`grooming` / `hospital` / `supplies`)에 맞는 주변 시설·트렌드·AI 추천을 받아오는 용도로 설계됐습니다.  
레거시 호환용으로 `snack` / `food` / `clothes`도 허용하며 내부적으로 `supplies`로 처리합니다.

---

## 기술 스택

| 역할 | 기술 | 선택 이유 |
|------|------|-----------|
| 웹 프레임워크 | FastAPI | async 네이티브, 자동 Swagger 생성 |
| DB ORM | SQLAlchemy 2.0 (asyncpg) | async 쿼리, Mapped 타입 힌트 |
| DB | PostgreSQL 15 | pg_trgm 한국어 퍼지 검색, Haversine 반경 쿼리 |
| 캐시 | Redis 7 | Sorted Set으로 트렌드 키워드 순위 관리 |
| 지오코딩 | Kakao Local API | 무료 티어, 한국 주소 정확도 높음 |
| LLM | Ollama `llama3` | 로컬 실행, API 비용 없음 (교체 가능) |
| 형태소 분석 | kiwipiepy | Java 불필요, pip 한 줄 설치 |
| 스케줄러 | APScheduler | `max_instances=1` 로 중복 실행 방지 |
| HTTP 클라이언트 | httpx | async + 지수 백오프 재시도 |

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│  수집 파이프라인 (매일 자동 실행, APScheduler)                │
│                                                              │
│  [행안부 공공API] ──► Collector ──► Kakao 지오코더 ──► Postgres│
│        (시설 + 병원)            (주소→lat/lng)                │
│                                                              │
│  [네이버 블로그API] ──► Collector ──► kiwipiepy ──► Redis     │
│                                 (형태소·빈도)                 │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  API 서빙 (FastAPI)                                          │
│                                                              │
│  Petory / Client                                             │
│      │  X-API-Key                                            │
│      ▼                                                       │
│  POST /recommend ──► Postgres (Haversine 반경 쿼리)           │
│                  └─► Redis    (카테고리 트렌드)               │
│                  └─► Ollama   (시설+트렌드+펫 → 추천문)       │
│                                                              │
│  GET /facilities · /stats/summary · /trends/{category}        │
└──────────────────────────────────────────────────────────────┘
```

---

## 핵심 기술 결정

### Haversine 반경 검색 (PostgreSQL)
`/recommend` 에서 사용자 좌표로부터 **반경 N km 이내**의 시설만 뽑기 위해 Haversine 공식을 **Pure SQL**로 계산합니다 (`6371000 * acos(...)`). PostGIS 없이도 동작하며, `lat IS NOT NULL` + `type` 필터와 함께 `ORDER BY distance_m LIMIT :top_n` 으로 상위만 반환합니다. 자세한 쿼리는 [`app/recommender/facilities.py`](app/recommender/facilities.py).

### 좌표가 없는 시설 처리
행안부 API 응답에 좌표가 없어 수집 직후 **Kakao 로컬 API**로 주소→`lat/lng` 을 보강합니다. 실패 시 `NULL` 로 두고, 반경 쿼리에서 자동 제외됩니다. 지오코더는 [`app/collector/geocoder.py`](app/collector/geocoder.py).

### LLM 호출 가드
주변 시설이 **한 건도 없으면** Ollama 호출 자체를 건너뛰고 `recommendation: null` 을 반환합니다. 시스템 프롬프트에도 "**제공된 시설 목록 외의 시설명은 절대 만들어내지 마**" 제약을 넣어 **환각 시설 생성**을 차단했습니다. 프롬프트/호출부는 [`app/recommender/builder.py`](app/recommender/builder.py), [`app/recommender/llm.py`](app/recommender/llm.py).

### Keyset 페이지네이션
`/facilities` 목록은 `LIMIT/OFFSET` 대신 `WHERE id > :cursor ORDER BY id LIMIT n`. 인덱스 탐색만으로 O(log n) 유지.

### pg_trgm 한국어 퍼지 검색
`LIKE '%검색어%'` 대신 GIN 인덱스 + `%` 유사도 연산자. 한국어 자모 trigram 인덱싱으로 오타·부분 일치 지원.

### Redis Sorted Set 트렌드 캐싱
`ZADD` 로 키워드 빈도 적재, `ZRANGE ... WITHSCORES` 로 상위 N개 조회. 매일 18:00에 갱신.

### kiwipiepy 형태소 분석
KoNLPy 대신 kiwipiepy. Java 런타임 불필요, NNG(일반명사)·NNP(고유명사)만 추출하고 불용어(추천, 후기 등)를 필터링.

---

## API 명세

모든 엔드포인트는 `X-API-Key` 헤더 인증 필요. 상세는 Swagger UI (`/docs`) 에서 확인할 수 있습니다.

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/recommend` | 위치·컨텍스트·펫 정보 기반 **AI 추천 + 주변 시설 + 트렌드** | 일반 |
| GET | `/facilities` | 시설 목록 (cursor 페이지네이션, 타입·지역 필터) | 일반 |
| GET | `/facilities/{id}` | 시설 상세 + 업종별 세부정보 | 일반 |
| GET | `/stats/summary` | 영업 중 시설 지역·타입별 통계 | 일반 |
| GET | `/trends/{category}` | 카테고리별 인기 키워드 Top N | 일반 |
| POST | `/collect/trigger` | 수동 수집 트리거 (`scope=facilities|trends|all`) | 관리자 |

### 컨텍스트 정의

`/recommend` · `/trends/{category}` 공통 입력.

| context | 의미 | 조회 시설 타입 | 트렌드 카테고리 |
|---------|------|---------------|----------------|
| `grooming` | 미용실 | `BUSINESS` | `grooming` |
| `hospital` | 동물병원 | `HOSPITAL` | `hospital` |
| `supplies` | 용품점 | `BUSINESS`(현재 데이터 기준) | `supplies` + (`snack`,`food`,`clothes`) |
| `snack` / `food` / `clothes` | 레거시 호환 입력 | `supplies`로 내부 매핑 | `supplies`로 내부 매핑 |

> `supplies`는 현재 공공데이터 수집 소스 제약으로 `BUSINESS` 시설을 활용하며, 용품점 전용 데이터 소스는 확장 예정입니다.

### `POST /recommend`

**요청**

```json
{
  "lat": 37.5665,
  "lng": 126.9780,
  "context": "grooming",
  "radius_km": 3,
  "top_n": 5,
  "pet": {
    "type": "dog",
    "breed": "말티즈",
    "age": "2살"
  }
}
```

| 필드 | 타입 | 필수 | 기본/제약 |
|------|------|------|-----------|
| `lat` | float | 필수 | - |
| `lng` | float | 필수 | - |
| `context` | string | 필수 | `grooming` / `hospital` / `supplies` (legacy: `snack` / `food` / `clothes`) |
| `radius_km` | float | 선택 | 기본 `3`, `0.5~20` |
| `top_n` | int | 선택 | 기본 `5`, `1~20` |
| `pet` | object | 선택 | `type`, `breed`, `age` (자유 형식) |

**응답**

```json
{
  "context": "grooming",
  "facilities": [
    {
      "name": "해피독 미용실",
      "distance_m": 320,
      "address": "서울시 마포구 ...",
      "lat": 37.5672,
      "lng": 126.9765
    }
  ],
  "trends": [
    { "keyword": "스포팅컷", "score": 41 },
    { "keyword": "여름컷",   "score": 35 }
  ],
  "recommendation": "말티즈에게는 요즘 스포팅컷이 인기입니다. 근처 해피독 미용실이 320m 거리로 가장 가깝고...",
  "generated_at": "2026-04-21T10:00:00+00:00"
}
```

**동작 규칙**

- 반경 내 시설이 없어도 트렌드 데이터가 있으면 추천 생성 시도
- Redis 장애 → `trends: []` 로 graceful degradation
- Ollama 장애·타임아웃 → `recommendation: null` (시설·트렌드는 항상 반환)

### 응답 예시 — `GET /trends/snack?limit=5`

```json
{
  "category": "snack",
  "updated_at": "2026-04-21T03:05:00+00:00",
  "keywords": [
    { "keyword": "오리젠",       "score": 42 },
    { "keyword": "로얄캐닌",     "score": 38 },
    { "keyword": "퍼스트메이트", "score": 31 }
  ]
}
```

Swagger UI: `http://localhost:8000/docs`

---

## Petory 연동 가이드

Petory(Java/Spring) 백엔드가 이 서버를 호출해 사용자 페이지에 **AI 추천 카드**를 렌더링합니다.

### 호출 흐름

```
Petory Front (React)
  └─ GPS(lat/lng) + 현재 페이지(context) + 로그인한 펫 정보
       │
       ▼
Petory Back (Spring) — PetDataApiClient
  └─ POST http://pet-data-api:8000/recommend
       Headers: X-API-Key: <일반 키>
       Body:    { lat, lng, context, radius_km?, top_n?, pet? }
       │
       ▼
pet-data-api (FastAPI)
  └─ facilities + trends + recommendation JSON 반환
```

### Spring 쪽 설정 예시

```properties
# application.properties
pet-data-api.base-url=http://pet-data-api:8000
pet-data-api.api-key=${PET_DATA_API_KEY}
pet-data-api.timeout-ms=35000
```

- API Key는 **원문**을 Petory 쪽에 보관, pet-data-api 에는 **SHA-256 해시**만 저장.
- Ollama 응답 대기 때문에 타임아웃은 **30초 이상** 권장.
- `recommendation` 이 `null` 이면 프론트에서는 카드 숨기고 시설·트렌드만 표시하는 폴백 UI 권장.

### 장애 격리

| 상황 | pet-data-api 동작 | Petory 프론트 권장 |
|------|------------------|-------------------|
| Ollama 다운 | `recommendation: null` | 시설·트렌드만 카드에 표시 |
| Redis 다운 | `trends: []` | 추천/시설만 표시 |
| pet-data-api 다운 | 5xx/연결 실패 | try-catch → 추천 카드 숨김 |

---

## 실행 방법

### 사전 준비

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- [Ollama](https://ollama.com/) + `llama3` 모델 (`ollama pull llama3`)
- [네이버 개발자센터](https://developers.naver.com) 블로그 검색 API 키
- [Kakao Developers](https://developers.kakao.com) REST API 키 (지오코딩)
- 공공데이터포털 서비스키 (영업장 · 동물병원)

### 빠른 시작

```bash
# 1. 의존성 설치
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. DB 초기화
psql -U postgres -c "CREATE DATABASE petdata;"
psql -U postgres -d petdata -f migrations/init.sql
psql -U postgres -d petdata -f migrations/v2_pet_facilities.sql
psql -U postgres -d petdata -f migrations/add_facility_coords.sql

# 3. 환경변수 설정
cp .env.example .env  # 값 직접 입력

# 4. Ollama 모델 준비 (최초 1회)
ollama pull llama3

# 5. 서버 실행 (기본 포트 8000, 코드 변경 시 자동 재시작)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Python 서버만 다시 켤 때

```bash
cd pet-data-api
source venv/bin/activate          # Windows: venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

가상환경 활성화 없이:

```bash
cd pet-data-api
./venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API · Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- `Address already in use` → 기존 프로세스 종료 또는 `--port 8001` 등으로 변경

### 테스트

```bash
pytest tests/ -v
```

---

## 환경변수

`.env` 파일에 설정 (`.env.example` 참고):

| 변수명 | 설명 |
|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/petdata` |
| `API_KEY_HASH` | 일반 API Key의 SHA-256 해시 |
| `ADMIN_API_KEY_HASH` | 관리자 API Key의 SHA-256 해시 |
| `PUBLIC_DATA_API_KEY` | 행안부 공공데이터 영업장 서비스키 |
| `HOSPITAL_API_KEY` | 동물병원 API 서비스키 |
| `NAVER_CLIENT_ID` | 네이버 검색 API Client ID |
| `NAVER_CLIENT_SECRET` | 네이버 검색 API Client Secret |
| `KAKAO_REST_API_KEY` | Kakao 로컬 API(지오코딩) REST 키 |
| `REDIS_URL` | 기본 `redis://localhost:6379/0` |
| `OLLAMA_BASE_URL` | 기본 `http://localhost:11434` |
| `OLLAMA_MODEL` | 기본 `llama3` |

API Key 해시 생성:

```bash
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print('KEY:', k); print('HASH:', hashlib.sha256(k.encode()).hexdigest())"
```

출력된 `KEY` 값을 호출 측(Petory 등)에 저장하고, `HASH` 값을 서버 `.env` 에 넣습니다.

---

## 프로젝트 구조

```
pet-data-api/
├── app/
│   ├── api/          # FastAPI 라우터 (recommend, facilities, stats, trends, collect)
│   ├── analyzer/     # 형태소 분석 (kiwipiepy), 키워드 집계
│   ├── cache/        # Redis 트렌드 Sorted Set
│   ├── collector/    # 공공데이터·네이버 수집, Kakao 지오코더, runner
│   ├── recommender/  # Haversine 쿼리, 프롬프트 빌더, Ollama 클라이언트
│   ├── core/         # config, database, auth
│   ├── models/       # SQLAlchemy 모델
│   ├── scheduler/    # APScheduler 잡 설정
│   ├── schemas/      # Pydantic 응답 스키마
│   └── main.py       # FastAPI lifespan · 라우터 등록
├── migrations/       # DB 초기화 + 스키마 변경 SQL
├── docs/             # 개요·사용·설계 문서
└── tests/
```

---

## 관련 문서

- [`docs/PROJECT-OVERVIEW.md`](docs/PROJECT-OVERVIEW.md) — 역할·경계·런타임/배치 동작 요약
- [`docs/USAGE.md`](docs/USAGE.md) — 실제 `curl` 예시 포함 사용 가이드
- [`docs/superpowers/specs/2026-04-21-pet-recommendation-pipeline-design.md`](docs/superpowers/specs/2026-04-21-pet-recommendation-pipeline-design.md) — 추천 파이프라인 설계
- [`docs/superpowers/specs/2026-04-21-pet-trend-pipeline-design.md`](docs/superpowers/specs/2026-04-21-pet-trend-pipeline-design.md) — 트렌드 파이프라인 설계
- [`docs/superpowers/specs/2026-05-01-petory-category-recommendation-redesign.md`](docs/superpowers/specs/2026-05-01-petory-category-recommendation-redesign.md) — 카테고리 클릭형 추천 재설계안
- [`docs/superpowers/plans/2026-05-02-phase1-refactor-log.md`](docs/superpowers/plans/2026-05-02-phase1-refactor-log.md) — 리팩토링 반영 로그
