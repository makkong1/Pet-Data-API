# CLAUDE.md — pet-data-api

행안부 공공 API 기반 **반려동물 시설(영업장·동물병원)** 데이터 수집·저장, 네이버 블로그 **트렌드 키워드**(Redis), **위치 기반 추천**(`POST /recommend`), **REST API** 제공. Python/FastAPI/PostgreSQL/Redis 백엔드 포트폴리오.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that **your** changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 목적 | 공공 시설 데이터를 PostgreSQL에 적재하고, 블로그 기반 트렌드를 Redis에 캐시한 뒤 API로 조회·통계·트렌드·수집·추천 제공 |
| 포지션 | Java/Spring(Petory)과 함께 멀티스택 백엔드 포트폴리오 구성 |
| 레포 | 독립 레포 (Petory와 무관) |

## 기술 스택

| 역할 | 기술 |
|------|------|
| 웹 프레임워크 | FastAPI |
| DB ORM | SQLAlchemy 2.0 (async/asyncpg) |
| DB | PostgreSQL 15+ (`pg_trgm` 등) |
| 캐시 | Redis (트렌드 Sorted Set; 그루밍 MVP Kakao 장소 검색 TTL 캐시) |
| 형태소 | kiwipiepy |
| 스케줄러 | APScheduler (`max_instances=1`; 로컬 **18:00** 트렌드, **18:05** 공공 수집 — [`app/platform/scheduler/jobs.py`](app/platform/scheduler/jobs.py)) |
| HTTP 클라이언트 | httpx (async; 공공 API 클라이언트는 재시도 — [`app/ingestion/client.py`](app/ingestion/client.py)) |
| 인증 | API Key (`X-API-Key` 헤더, SHA-256 해싱) |
| 환경변수 | pydantic-settings (.env) |
| (선택) LLM | 레거시 추천 경로에서 Ollama (`OLLAMA_*`) — 그루밍 MVP 기본은 규칙 기반 카피 |

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

`.env.example`와 동기. 주요 항목:

```
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/petdata
API_KEY_HASH=<sha256>
ADMIN_API_KEY_HASH=<sha256>
PUBLIC_DATA_API_KEY=<data.go.kr>
HOSPITAL_API_KEY=<동물병원 API>
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
KAKAO_REST_API_KEY=<카카오 REST — 지오코딩·Local 키워드 검색>
REDIS_URL=redis://localhost:6379/0
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
GROOMING_MVP_ENABLED=false
NAVER_TIMEOUT_MS=10000
KAKAO_TIMEOUT_MS=8000
```

API Key 해시 생성:

```python
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print(k, hashlib.sha256(k.encode()).hexdigest())"
```

## 프로젝트 구조

```
pet-data-api/
├── app/
│   ├── main.py                 # FastAPI 앱·라우터 마운트·lifespan(스케줄)
│   ├── ingestion/              # 공공 수집·네이버·Kakao·지오코더·그루밍 블로그
│   │   ├── analyzer/          # 트렌드 형태소 등
│   │   ├── business.py, hospital.py, runner.py, client.py
│   │   ├── naver.py, geocoder.py, kakao.py, grooming_blog.py
│   ├── serving/                # HTTP·추천 (수집과 분리)
│   │   ├── api/                # facilities, stats, collect, trends, recommend
│   │   └── recommender/        # 반경 시설, 그루밍 랭커, LLM·프롬프트 빌더
│   └── platform/               # DB, 설정, 스키마, Redis, 스케줄
│       ├── core/, models/, schemas/, cache/, scheduler/
├── migrations/
├── docs/                       # PROJECT-OVERVIEW, USAGE, GROOMING-RECOMMEND-MVP 등
└── tests/
```

**경계**: [`docs/INGESTION-VS-SERVING.md`](docs/INGESTION-VS-SERVING.md), 흐름 [`docs/DATA-AND-API-FLOW.md`](docs/DATA-AND-API-FLOW.md).

## 아키텍처 핵심 패턴

- **인증**: SHA-256 API Key. 일반 키 vs 관리자 키(`/collect/trigger` 등). 401/403 분리.
- **시설 목록**: Keyset(cursor). `WHERE id > :cursor ORDER BY id LIMIT n`.
- **통계**: `pet_facilities` 집계 쿼리(`GET /stats/summary`).
- **트렌드**: 스케줄에서 네이버 수집 → 형태소 집계 → Redis; API는 Redis 조회.
- **수집**: `app/ingestion/runner.py` — httpx(공공), 소스별 `collection_logs`. **`status`가 공공 API상 `폐업`이면 INSERT/UPDATE 하지 않고, 기존 `source_id` 행은 DELETE** (상세 테이블은 FK CASCADE).
- **추천**: `POST /recommend` — `context=grooming` + `GROOMING_MVP_ENABLED=true`일 때 그루밍 파이프(공공 반경 → 블로그 멘션 → Kakao Local·Redis 캐시 → `grooming_ranker` → 규칙 카피). 그 외는 레거시(근처 시설 + 트렌드 + 선택적 Ollama).
- **스케줄**: `max_instances=1`로 중복 방지.

그루밍 계약·플래그·로그: [`docs/GROOMING-RECOMMEND-MVP.md`](docs/GROOMING-RECOMMEND-MVP.md).

## API 엔드포인트 (요약)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/facilities` | 시설 목록 (필터, cursor) | 일반 |
| GET | `/facilities/{id}` | 시설 상세 | 일반 |
| GET | `/stats/summary` | 지역·유형별 집계 | 일반 |
| GET | `/trends/{category}` | 트렌드 키워드 | 일반 |
| POST | `/recommend` | 맞춤 추천 (시설·트렌드·그루밍 MVP 분기) | 일반 |
| POST | `/collect/trigger` | 공공·트렌드 수동 수집 | 관리자 |

Swagger UI: `http://localhost:8000/docs`

## 시설 DB 인덱스 (요지)

`pet_facilities`: `source_id` 유니크, `(region_city, region_district, type, status)` 등 — 상세는 `migrations/v2_pet_facilities.sql`.

## 데이터 소스

- **행안부 공공 API**: 반려동물 영업장(`petShop`), 동물병원(`animalHospital`) — `PUBLIC_DATA_API_KEY`, `HOSPITAL_API_KEY`.
- **네이버 블로그 검색 Open API**: 트렌드 텍스트·(그루밍 시) 멘션 후보.
- **Kakao REST**: 주소 지오코딩·Local 키워드 장소 검색 — `KAKAO_REST_API_KEY`.

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

- [`docs/PROJECT-OVERVIEW.md`](docs/PROJECT-OVERVIEW.md) — 역할·경계·런타임/배치
- [`docs/USAGE.md`](docs/USAGE.md) — 실행·curl 예시
- [`docs/GROOMING-RECOMMEND-MVP.md`](docs/GROOMING-RECOMMEND-MVP.md) — 그루밍 MVP 계약·플래그·관측성
