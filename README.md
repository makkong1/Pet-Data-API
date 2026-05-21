# pet-data-api

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-llama3-000000)

공공데이터(시설) + 네이버 블로그 트렌드 + 위치 기반 추천 + 이벤트 환류를 제공하는 FastAPI 백엔드.

이 문서는 **현재 코드 기준**으로 작성되었습니다.

- 앱 엔트리: `app/main.py`
- 핵심 추천 API: `app/serving/api/recommend.py`
- 수집 런너: `app/ingestion/runner.py`

동일한 **요약 명령**은 포트폴리오/아키텍처 문서(`pet-data-api architecture.md` §9.2 빠른 시작)에도 적어 두었습니다.

---

## Quick start (실행 명령만)

프로젝트 루트(이 README가 있는 디렉터리)에서 가상환경을 켠 뒤 Uvicorn으로 기동합니다. 상위 폴더에서만 내려올 때는 `cd pet-data-api` 한 뒤 아래와 같이 실행하면 됩니다.

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
# .env · PostgreSQL · Redis 준비 후
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger: `http://localhost:8000/docs`
- DB 마이그레이션·환경변수·테스트까지 포함한 전체 절차는 아래 **§7 실행 방법** 참고.
- 로컬에서 자주 띄울 때는 셸 alias로 한 줄로 줄일 수 있다. 예시(`~/.zshrc` 등, `<레포경로>`만 본인 환경에 맞게):  
  `alias pet-api='cd <레포경로> && source venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000'`

---

## 1) 프로젝트 개요

이 프로젝트는 세 가지를 결합합니다.

1. 공공 API 시설 수집
- data.go.kr 영업장/동물병원 데이터를 수집해 PostgreSQL `pet_facilities`에 upsert
- 좌표가 비어 있으면 Kakao 주소 지오코딩으로 `lat/lng` 보강

2. 트렌드 수집/캐시
- Naver Blog Search 결과를 형태소 분석(kiwipiepy)하여 카테고리 키워드 빈도 집계
- Redis Sorted Set(`trends:{category}:keywords`) 캐시 + Postgres `trend_snapshots` 시계열 저장

3. 추천 서빙
- `/recommend`: DB 반경 시설 + Redis 트렌드 + 규칙/LLM 카피를 결합
- `/events/recommendation`: 노출/클릭/예약 이벤트를 적재해 다음 추천의 history 신호로 환류

---

## 2) 아키텍처 문서

상세 다이어그램/플로우는 아래 문서로 분리되어 있습니다.

- [아키텍처 상세](docs/ARCHITECTURE.md)
- [데이터 수집·저장·API 흐름](docs/DATA-AND-API-FLOW.md)
- [Ingestion vs Serving 경계](docs/INGESTION-VS-SERVING.md)
- [사용 가이드](docs/USAGE.md)

---

## 3) 기술 스택

| 역할 | 기술 |
|---|---|
| API | FastAPI, Uvicorn |
| DB | PostgreSQL, SQLAlchemy 2.0(async), asyncpg |
| Cache | Redis (redis-py asyncio) |
| 분석 | kiwipiepy |
| 외부 호출 | httpx (재시도 포함) |
| 스케줄 | APScheduler |
| 랭킹 | 규칙 기반 신호 조합(distance/mention/trend/history/pet) |
| LLM | Ollama (`/recommend/copy` 또는 `include_copy=true` 시) |
| 관측성 | request-id middleware, `/healthz`, `/readyz`, `/metrics` |

---

## 4) 런타임 동작 핵심

### 4.1 요청 ID/헬스/메트릭

`app/platform/observability.py`

- 모든 요청에 `X-Request-Id` 부여 또는 에코
- `GET /healthz`: liveness
- `GET /readyz`: DB/Redis readiness
- `GET /metrics`: Prometheus 메트릭 (instrumentator 사용 가능 시)

### 4.2 스케줄

`app/platform/scheduler/jobs.py`

- 매일 `18:00`: `run_trend_collection()`
- 매일 `18:05`: `run_collection(db)`
- `max_instances=1`로 중복 실행 방지

주의: 타임존 명시는 별도로 없어서 **프로세스 로컬 시각** 기준입니다.

### 4.3 추천 파이프 분기

`POST /recommend`는 `context`와 `GROOMING_MVP_ENABLED`에 따라 분기합니다.

1. 확장 파이프 (feature flag ON + enriched context)
- 컨텍스트: `grooming`, `hospital`, `supplies`, `pharmacy`, `cafe`, `pension`, `restaurant`, `boarding`, `hotel`
- 단계: 공공 후보 조회 -> 블로그 멘션 후보 추출 -> Kakao 장소 보강 -> 병합/중복제거 -> 신호 랭킹
- 카피: 규칙 기반(`build_context_copy`)
- 버전: `{context}-mvp-v1`

2. 레거시 파이프 (feature flag OFF 또는 비확장 컨텍스트)
- 시설 없고 트렌드만 있으면 규칙 기반 카피
- `include_copy=true`면 Ollama 호출
- 버전: `legacy`

`POST /recommend/copy`는 카피만 별도 호출하는 분리 엔드포인트입니다.

---

## 5) API 요약

인증: 보호 엔드포인트는 `X-API-Key` 필요

- 일반/관리자 키 모두 통과: `require_api_key`
- 관리자 키만 통과: `require_admin_key` (`/collect/trigger`)

| 메서드 | 경로 | 설명 | 인증 |
|---|---|---|---|
| GET | `/healthz` | Liveness | 없음 |
| GET | `/readyz` | DB/Redis readiness | 없음 |
| GET | `/metrics` | Prometheus metrics | 없음 |
| GET | `/facilities` | 시설 목록 (keyset cursor) | 일반 |
| GET | `/facilities/{facility_id}` | 시설 상세 | 일반 |
| GET | `/facilities/search` | 이름/태그/지역/반경 검색 | 일반 |
| GET | `/stats/summary` | 영업중 시설 집계 | 일반 |
| GET | `/trends/{category}` | Redis 트렌드 조회 | 일반 |
| GET | `/trends/{category}/timeseries` | Postgres 트렌드 시계열 | 일반 |
| POST | `/recommend` | 시설+트렌드+추천 응답 | 일반 |
| POST | `/recommend/copy` | LLM 카피 전용 호출 | 일반 |
| POST | `/events/recommendation` | 노출/클릭/예약 이벤트 적재 | 일반 |
| POST | `/collect/trigger` | 수동 수집 (scope 분기) | 관리자 |

Swagger: `http://localhost:8000/docs`

---

## 6) 컨텍스트/카테고리 규칙

### 6.1 추천 컨텍스트

`app/serving/recommender/facilities.py`

| 입력 context | 내부 매핑 | 시설 타입 |
|---|---|---|
| `grooming` | `grooming` | `BUSINESS` |
| `hospital` | `hospital` | `HOSPITAL` |
| `supplies` | `supplies` | `BUSINESS` |
| `pharmacy`/`cafe`/`pension`/`restaurant`/`boarding`/`hotel` | 동일 | `BUSINESS` |
| `snack`/`food`/`clothes` | `supplies` (alias) | `BUSINESS` |

### 6.2 트렌드 카테고리

`app/ingestion/naver.py`의 `CATEGORY_KEYWORDS` 기준:

- `supplies`, `snack`, `food`, `grooming`, `hospital`, `clothes`
- `pharmacy`, `cafe`, `pension`, `restaurant`, `boarding`, `hotel`

---

## 7) 실행 방법

### 7.1 사전 준비

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Ollama + `llama3` 모델
- 공공 API 키 2종 (`PUBLIC_DATA_API_KEY`, `HOSPITAL_API_KEY`)
- Naver API 키 2종
- Kakao REST API 키

### 7.2 설치/실행

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env 값 채우기

# DB 생성
psql -U postgres -c "CREATE DATABASE petdata;"

# 스키마 적용 (신규 설치 권장 순서)
psql -U postgres -d petdata -f migrations/init.sql
psql -U postgres -d petdata -f migrations/v2_pet_facilities.sql
psql -U postgres -d petdata -f migrations/add_facility_coords.sql
psql -U postgres -d petdata -f migrations/003_trend_snapshots.sql
psql -U postgres -d petdata -f migrations/004_facility_tags.sql
psql -U postgres -d petdata -f migrations/005_recommendation_log.sql
psql -U postgres -d petdata -f migrations/006_facility_interactions.sql

# (선택) 구 abandoned schema 정리
# psql -U postgres -d petdata -f migrations/002_drop_abandoned_animals.sql

# Ollama 모델 준비
ollama pull llama3

# 서버 실행
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7.3 테스트

```bash
source venv/bin/activate
pytest tests/ -v
```

---

## 8) 환경변수

`.env.example` 기준

| 변수 | 설명 |
|---|---|
| `DATABASE_URL` | async SQLAlchemy URL |
| `API_KEY_HASH` | 일반 API 키 SHA-256 |
| `ADMIN_API_KEY_HASH` | 관리자 API 키 SHA-256 |
| `PUBLIC_DATA_API_KEY` | data.go.kr 영업장 API 키 |
| `HOSPITAL_API_KEY` | data.go.kr 병원 API 키 |
| `NAVER_CLIENT_ID` | Naver API ID |
| `NAVER_CLIENT_SECRET` | Naver API Secret |
| `KAKAO_REST_API_KEY` | Kakao REST API Key |
| `REDIS_URL` | Redis URL |
| `GROOMING_MVP_ENABLED` | 확장 추천 파이프 ON/OFF |
| `NAVER_TIMEOUT_MS` | Naver timeout(ms) |
| `KAKAO_TIMEOUT_MS` | Kakao timeout(ms) |
| `OLLAMA_BASE_URL` | Ollama base URL |
| `OLLAMA_MODEL` | Ollama model |

API 키 해시 생성:

```bash
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print('KEY:', k); print('HASH:', hashlib.sha256(k.encode()).hexdigest())"
```

---

## 9) 추천 응답 구조 포인트

`app/platform/schemas/recommend.py`

- `request_id`: `X-Request-Id`와 동일 (로그/콜백 연결)
- `facilities[].score`: 최종 점수(0~1)
- `facilities[].mention_score`: 멘션 정규화 점수(0~1)
- `facilities[].reasons`: 랭킹 기여 라벨
- `recommend_version`: `legacy` 또는 `{context}-mvp-v1`
- 요청 `pet`: `type`·`breed` 및 선택적으로 `age`(자유 문자열) 또는 **`age_months`(정수 개월)** — Petory 등은 주로 후자를 전송하며 랭커의 노령 휴리스틱과 정합 (`age_months≥120` ≈ 10살 문자열 패턴과 동급).

`POST /recommend/copy` 응답은 `source=llm|rule`를 반환합니다.

---

## 10) 데이터 환류(Feedback Loop)

1. 클라이언트가 `/recommend` 호출
2. 응답의 `request_id`를 보관
3. 노출/클릭/예약 이벤트를 `/events/recommendation`으로 송신
4. 확장 파이프의 history 신호(`InteractionHistorySignal`)가 최근 14일 클릭 이력을 반영

즉, 추천 -> 사용자 반응 -> 다음 추천 점수에 반영되는 폐루프가 존재합니다.

---

## 11) 디렉터리 구조

```text
pet-data-api/
├── app/
│   ├── ingestion/
│   ├── serving/
│   │   ├── api/
│   │   └── recommender/
│   ├── platform/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── cache/
│   │   └── scheduler/
│   └── main.py
├── migrations/
├── tests/
└── docs/
```

---

## 12) 라이선스/운영 주의

- Naver/Kakao/data.go.kr 이용약관, 호출 한도, 저장 정책은 실제 운영 환경에서 별도 검토가 필요합니다.
- 본 레포는 포트폴리오/학습 목적 구현이며, 운영 배포 전 보안/비용/장애복구 정책을 추가 점검해야 합니다.
