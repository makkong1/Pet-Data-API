# pet-data-api 사용 가이드

이 문서는 레포지토리 **현재 코드**(`app/main.py`, 라우터, 마이그레이션)를 기준으로 정리했습니다. 전체 개요·아키텍처는 [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md), 에이전트용 요약은 루트 [`CLAUDE.md`](../CLAUDE.md)를 보세요.

## 이 프로젝트가 하는 일

- **FastAPI**로 **반려동물 관련 시설** 데이터를 PostgreSQL에 저장하고, **네이버 블로그 기반 트렌드 키워드**를 Redis에 캐시하며, **API Key**로 보호된 REST API로 조회·통계·트렌드·수집을 제공합니다.
- **data.go.kr** 공공 API 키(`PUBLIC_DATA_API_KEY`, 병원용 `HOSPITAL_API_KEY`)로 **반려동물 영업장**·**동물병원** 데이터를 가져와 `pet_facilities` 등에 **upsert**합니다.
- **APScheduler**: 로컬 시각 **매일 18:00**에 네이버 블로그 → 형태소 분석 → Redis 트렌드 갱신(`max_instances=1`), **매일 18:05**에 공공데이터 수집.

## 사전 요구 사항

- Python 3.x (프로젝트에 맞는 버전; 가상환경 권장)
- PostgreSQL 15+ 권장
- Redis (트렌드 API·스케줄 잡용)
- data.go.kr에서 발급한 **공공데이터포털 서비스키**
- [네이버 개발자센터](https://developers.naver.com) 검색 API용 Client ID/Secret

## 설치

```bash
cd /path/to/pet-data-api
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 데이터베이스 준비

1. DB 생성 (예시):

   ```bash
   psql -U postgres -c "CREATE DATABASE petdata;"
   ```

2. 마이그레이션 순서대로 적용:

   ```bash
   psql -U postgres -d petdata -f migrations/init.sql
   psql -U postgres -d petdata -f migrations/v2_pet_facilities.sql
   ```

   - `init.sql`: 확장·기본 객체.
   - `v2_pet_facilities.sql`: 현재 API가 사용하는 **`pet_facilities`**, `business_details`, `hospital_details` 테이블.

## 환경 변수 (`.env`)

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

| 변수 | 설명 |
|------|------|
| `DATABASE_URL` | SQLAlchemy 비동기 URL. 예: `postgresql+asyncpg://USER:PASSWORD@HOST:5432/petdata` |
| `API_KEY_HASH` | 일반 API Key의 **SHA-256 해시** (hex) |
| `ADMIN_API_KEY_HASH` | 관리자 Key의 **SHA-256 해시** — `/collect/trigger` 등에 필요 |
| `PUBLIC_DATA_API_KEY` | data.go.kr 서비스키 (평문) |
| `HOSPITAL_API_KEY` | 동물병원 API 서비스키 (평문) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 검색 API |
| `REDIS_URL` | Redis 연결 URL (기본 `redis://localhost:6379/0`) |

API Key **원문**으로 쓰는 것이 아니라, 설정에는 **해시만** 넣습니다. 해시와 샘플 키 생성 예:

```bash
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print('KEY=', k); print('HASH=', hashlib.sha256(k.encode()).hexdigest())"
```

출력된 `KEY=` 값을 클라이언트에 저장하고, `HASH=` 값을 `API_KEY_HASH` 또는 `ADMIN_API_KEY_HASH`에 넣습니다.

## 서버 실행

```bash
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API 문서(Swagger): `http://localhost:8000/docs`
- 앱 제목: `Pet Data API` (`app/main.py`).

## 인증

모든 보호된 엔드포인트는 HTTP 헤더로 키를 넘깁니다.

```http
X-API-Key: <발급해 둔 평문 API 키>
```

- 일반 키 또는 관리자 키 해시와 일치하면 통과합니다.
- 관리자 전용 엔드포인트는 **관리자 키**만 허용합니다. 일반 키만 맞으면 **403**이 날 수 있습니다.

## API 요약

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/facilities` | 시설 목록 (cursor 페이지네이션, 필터) | 일반/관리자 |
| GET | `/facilities/{facility_id}` | 시설 상세 (`BUSINESS`/`HOSPITAL`에 따라 `details` 포함) | 일반/관리자 |
| GET | `/stats/summary` | 시도·시군구·유형별 건수 (`영업` 상태만 집계) | 일반/관리자 |
| GET | `/trends/{category}` | 카테고리별 인기 키워드 (Redis; `snack`·`food`·`grooming`·`hospital`·`clothes`) | 일반/관리자 |
| POST | `/collect/trigger` | 공공데이터 수동 수집 (영업장 + 병원 순차 실행) | **관리자만** |

### 목록 쿼리 예시 (`/facilities`)

- `cursor`: 이전 응답의 `next_cursor` (첫 요청은 `0` 또는 생략 가능)
- `limit`: 1~100, 기본 20
- `type`: 시설 유형 (DB의 `type`, 예: `HOSPITAL`, `BUSINESS`)
- `region_city`, `region_district`: 지역 필터
- `status`: 쿼리 파라미터 이름은 `status` (코드에서는 `status_filter`로 매핑)

### curl 예시

```bash
export API_KEY='발급한_평문_키'

curl -s -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/facilities?limit=10"

curl -s -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/facilities/1"

curl -s -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/stats/summary"

curl -s -X POST -H "X-API-Key: $ADMIN_KEY" \
  "http://localhost:8000/collect/trigger"
```

`POST /collect/trigger`는 `PUBLIC_DATA_API_KEY`가 유효하고 네트워크·API 응답이 정상일 때 소스별로 `collection_logs`에 기록되며, 응답은 소스별 수집 결과 리스트 형태입니다.

## 자동 수집 스케줄

- **매일 18:00**: 네이버 블로그 트렌드 수집·Redis 갱신(`daily_trend_collection`).
- **매일 18:05**: 공공데이터 수집(`daily_collection`).
- 모두 `app/scheduler/jobs.py`에서 `max_instances=1`.
- 별도 타임존 설정이 없으면 **프로세스가 돌아가는 머신의 로컬 시간** 기준입니다. 서버 배포 시 운영체제/ZONE 설정을 맞추세요.

## 테스트

```bash
pytest tests/ -v
```

## 디렉터리 개요 (현재 기능 기준)

| 경로 | 역할 |
|------|------|
| `app/main.py` | FastAPI 앱, 라우터 등록, lifespan에서 스케줄러 시작/종료 |
| `app/api/facilities.py` | 시설 목록·상세 |
| `app/api/stats.py` | 요약 통계 |
| `app/api/collect.py` | 수집 트리거 |
| `app/api/trends.py` | 트렌드 키워드 조회 |
| `app/collector/` | 공공 API·네이버 수집, `run_collection` / `run_trend_collection` |
| `app/analyzer/` | 형태소·키워드 집계 |
| `app/cache/` | Redis 트렌드 캐시 |
| `app/core/` | 설정, DB 세션, 인증 |
| `migrations/` | SQL 초기화 스크립트 |

---

문제가 생기면 `DATABASE_URL`·해시·서비스키, 그리고 `psql`로 테이블 존재 여부(`pet_facilities` 등)를 먼저 확인하면 원인 파악이 빠릅니다.
