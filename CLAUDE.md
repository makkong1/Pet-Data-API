# CLAUDE.md — pet-data-api

네이버 블로그 기반 **트렌드 키워드**(Redis)·**컨텍스트별 인기 상호**(Redis)를 적재하고 **`GET /trends`**, **`GET /popular`** 로 제공하는 **Python/FastAPI** 서비스. 현재 레포 버전은 PostgreSQL 이나 공공 시설 수집·추천 엔드를 포함하지 않는다.

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
| 목적 | 네이버 블로그 결과를 형태소/파싱 후 **Redis**에 두고 **`GET /trends`**, **`GET /popular`** 로 노출 |
| 포지션 | Petory(Java/Spring)와 별개 레포; Petory 에서 소비 가능한 **외부 바이블로그 신호 원천 API** 역할 가능 |
| 영속 저장소 | 현재 버전은 **PostgreSQL 없음**(레포 `migrations/` 는 레거시 참고용 일 수 있음) |

## 기술 스택

| 역할 | 기술 |
|------|------|
| 웹 프레임워크 | FastAPI |
| 캐시·상태 | Redis (키 설계: [`app/platform/cache/redis.py`](app/platform/cache/redis.py), 인기 배치는 JSON 문자열) |
| 형태소 | kiwipiepy (트렌드 경로) |
| 스케줄러 | APScheduler 로컬 **18:00** 트렌드, **18:10** 인기 — [`app/platform/scheduler/jobs.py`](app/platform/scheduler/jobs.py); `max_instances=1` |
| HTTP 클라이언트 | httpx(async) — 블로그 검색 호출 등 |
| 인증 | `X-API-Key` 헤더 평문의 SHA-256 이 `API_KEY_HASH` 또는 `ADMIN_API_KEY_HASH` 와 일치 |
| 설정 | pydantic-settings — [`app/platform/core/config.py`](app/platform/core/config.py) |

## 실행

```bash
source venv/bin/activate
pip install -r requirements.txt
# Redis 준비, .env 작성 후
uvicorn app.main:app --reload

PYTHONPATH=. pytest tests/ -v
```

### 배치 CLI (Petory DB 적재용)

```bash
# ~/data 디렉토리 없으면 먼저 생성
mkdir -p ~/data

# 전체 컨텍스트 수집 → ~/data/pet-locations.json 출력
source venv/bin/activate
PYTHONPATH=. python cli.py popular --output ~/data/pet-locations.json

# 특정 컨텍스트만 (검증용)
PYTHONPATH=. python cli.py popular --output ~/data/pet-locations.json --contexts grooming hospital
```

출력 파일은 Spring `FacilitySyncScheduler`(매일 01:00)가 자동으로 읽어 Petory DB에 적재한다.

## 환경변수 (.env)

`.env.example` 참고.

```
API_KEY_HASH=<sha256 hex of plain api key>
ADMIN_API_KEY_HASH=<sha256 hex of admin key>
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
REDIS_URL=redis://localhost:6379/0
NAVER_TIMEOUT_MS=10000
```

API 키 해시 생성 예:

```bash
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print(k, hashlib.sha256(k.encode()).hexdigest())"
```

## 프로젝트 구조

```
pet-data-api/
├── app/
│   ├── main.py            # 라우터: trends / popular / collect
│   ├── ingestion/
│   │   ├── naver.py, blog.py, runner.py
│   │   └── analyzer/      # 트렌드 형태소 등
│   ├── serving/api/       # HTTP (읽기 + 관리 수집)
│   └── platform/
│       ├── core/, cache/, schemas/, scheduler/, observability.py
├── migrations/            # 과거 레거시 SQL (현 앱 에서 미사용)
├── docs/
└── tests/
```

흐름: [`docs/분석/DATA-AND-API-FLOW.md`](docs/분석/DATA-AND-API-FLOW.md). 디렉터리 역할: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 아키텍처 핵심 패턴

- **배치(쓰기)만 외부 I/O**: `run_trend_collection`, `run_popular_collection` 가 네이버를 호출해 Redis 업데이트.
- **API(읽기)**: Redis 만 조회. 키 누락 시 503.
- **운영 준비**: `/readyz` 는 **Redis ping** 만 검사(DB 없음).
- **수동 수집**: `POST /collect/trigger` 에 JSON `targets` 필요. 헤더 `X-API-Key` 는 **관리자** 키만 통과 (`require_admin_key`).

설계 명세(SSOT): [`docs/superpowers/specs/2026-05-23-popularity-intelligence-redesign.md`](docs/superpowers/specs/2026-05-23-popularity-intelligence-redesign.md).

## API 엔드포인트 (요약)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/healthz` | Liveness | 없음 |
| GET | `/readyz` | Redis readiness | 없음 |
| GET | `/metrics` | Prometheus(가능 시) | 없음 |
| GET | `/trends/{category}` | 카테고리 트렌드 키워드 순위 | 일반 또는 관리 키 |
| GET | `/popular/{context}` | 인기 상호 목록(JSON) | 일반 또는 관리 키 |
| POST | `/collect/trigger` | 트렌드/인기 배치 실행 | 관리자 키 |

Swagger UI: `http://localhost:8000/docs`

## 데이터 소스

- **네이버 블로그 검색 Open API** (`NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET`)

## Skills (커스텀 명령)

`.claude/commands/`:

| Command | 설명 |
|---------|------|
| `/commit` | 파일 필터링 → Python scope 분류 → 커밋+푸시 |
| `/review` | FastAPI/Redis 패턴 코드 리뷰 |
| `/fix` | 버그 재현 → Hotfix/Proper Fix |
| `/harness` | Harness 워크플로우 |

superpowers 스킬은 플러그인으로 자동 로드.

## 문서

- [`docs/PROJECT-OVERVIEW.md`](docs/PROJECT-OVERVIEW.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/USAGE.md`](docs/USAGE.md)
- [`docs/PETORY-INTEGRATION.md`](docs/PETORY-INTEGRATION.md)
- [`docs/V3-CHANGES.md`](docs/V3-CHANGES.md)
