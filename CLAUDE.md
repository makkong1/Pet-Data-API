# CLAUDE.md — pet-data-api

행안부 공공 API 기반 **반려동물 시설(영업장·동물병원)** 데이터 수집·저장, 네이버 블로그 **트렌드 키워드**(Redis), **REST API** 제공. Python/FastAPI/PostgreSQL/Redis 백엔드 포트폴리오.

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 목적 | 공공 시설 데이터를 PostgreSQL에 적재하고, 블로그 기반 트렌드를 Redis에 캐시한 뒤 API로 조회·통계·트렌드·수집 제공 |
| 포지션 | Java/Spring(Petory)과 함께 멀티스택 백엔드 포트폴리오 구성 |
| 레포 | 독립 레포 (Petory와 무관) |

## 기술 스택

| 역할 | 기술 |
|------|------|
| 웹 프레임워크 | FastAPI |
| DB ORM | SQLAlchemy 2.0 (async/asyncpg) |
| DB | PostgreSQL 15+ (`pg_trgm` 등) |
| 캐시 | Redis (트렌드 키워드 Sorted Set) |
| 형태소 | kiwipiepy |
| 스케줄러 | APScheduler (`max_instances=1`; 공공 수집 02:00, 트렌드 03:00 로컬 시각) |
| HTTP 클라이언트 | httpx (async, 지수 백오프 재시도) |
| 인증 | API Key (`X-API-Key` 헤더, SHA-256 해싱) |
| 환경변수 | pydantic-settings (.env) |

## 실행

```bash
source venv/bin/activate

psql -U postgres -c "CREATE DATABASE petdata;"
psql -U postgres -d petdata -f migrations/init.sql
psql -U postgres -d petdata -f migrations/v2_pet_facilities.sql

uvicorn app.main:app --reload
pytest tests/ -v
```

## 환경변수 (.env)

`.env.example` 참고.

```
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/petdata
API_KEY_HASH=<sha256>
ADMIN_API_KEY_HASH=<sha256>
PUBLIC_DATA_API_KEY=<data.go.kr>
HOSPITAL_API_KEY=<동물병원 API>
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
REDIS_URL=redis://localhost:6379/0
```

API Key 해시 생성:

```python
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print(k, hashlib.sha256(k.encode()).hexdigest())"
```

## 프로젝트 구조

```
pet-data-api/
├── app/
│   ├── api/          # facilities, stats, collect, trends
│   ├── collector/    # 공공 API, 네이버, runner
│   ├── analyzer/     # 형태소·키워드 집계
│   ├── cache/        # Redis
│   ├── scheduler/
│   ├── models/
│   ├── schemas/
│   ├── core/
│   └── main.py
├── migrations/
└── tests/
```

## 아키텍처 핵심 패턴

- **인증**: SHA-256 API Key. 일반 키 vs 관리자 키(`/collect/trigger` 등). 401/403 분리.
- **시설 목록**: Keyset(cursor). `WHERE id > :cursor ORDER BY id LIMIT n`.
- **통계**: `pet_facilities` 집계 쿼리(`GET /stats/summary`).
- **트렌드**: 스케줄에서 네이버 수집 → 형태소 집계 → Redis; API는 Redis 조회.
- **수집**: httpx 재시도, 소스별 `collection_logs`. 공통 클라이언트는 `app/collector/client.py`.
- **스케줄**: `max_instances=1`로 중복 방지.

## API 엔드포인트 (요약)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/facilities` | 시설 목록 (필터, cursor) | 일반 |
| GET | `/facilities/{id}` | 시설 상세 | 일반 |
| GET | `/stats/summary` | 지역·유형별 집계 | 일반 |
| GET | `/trends/{category}` | 트렌드 키워드 | 일반 |
| POST | `/collect/trigger` | 공공데이터 수동 수집 | 관리자 |

Swagger UI: `http://localhost:8000/docs`

## 시설 DB 인덱스 (요지)

`pet_facilities`: `source_id` 유니크, `(region_city, region_district, type, status)` 등 — 상세는 `migrations/v2_pet_facilities.sql`.

## 데이터 소스

- **행안부 공공 API**: 반려동물 영업장(`petShop`), 동물병원(`animalHospital`) 등 — 서비스키 `PUBLIC_DATA_API_KEY`, `HOSPITAL_API_KEY`.
- **네이버 블로그 검색 Open API**: 트렌드 텍스트 수집.

## Skills (커스텀 명령)

`.claude/commands/`:

| Command | 설명 |
|---------|------|
| `/commit` | 파일 필터링 → Python scope 분류 → 커밋+푸시 |
| `/review` | FastAPI/SQLAlchemy 룰 기반 코드 리뷰 |
| `/fix` | 버그 재현 → Hotfix/Proper Fix |
| `/harness` | Harness 프레임워크 워크플로우 |

superpowers 스킬은 플러그인으로 자동 로드.

## 문서

상세 개요: [`docs/PROJECT-OVERVIEW.md`](docs/PROJECT-OVERVIEW.md), 실행: [`docs/USAGE.md`](docs/USAGE.md).
