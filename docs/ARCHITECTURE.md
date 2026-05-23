# pet-data-api 아키텍처

> **Popularity Intelligence** 리디자인 이후 레포 상태를 반영합니다. 영속 DB는 두지 않고 **Redis** 만 사용합니다.

## 보조 문서

- [`USAGE.md`](USAGE.md) — 실행, 환경 변수, curl
- [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md) — 역할·범위
- [`분석/DATA-AND-API-FLOW.md`](분석/DATA-AND-API-FLOW.md) — 배치 → Redis → API

## 디렉터리 역할

| 경로 | 역할 |
|------|------|
| `app/main.py` | FastAPI 앱, 라우터 등록, lifespan 에서 스케줄러 시작/종료 |
| `app/serving/api/` | **읽기 전용 HTTP**: `trends`, `popular`, 관리자 `collect` |
| `app/ingestion/` | 배치 파이프: 네이버 블로그 호출, 파싱·집계, Redis 기록 (`runner.py` 등) |
| `app/platform/` | 설정(`core/config`), 인증(`core/auth`), Redis(`cache/redis.py`), 스키마(`schemas/`), 스케줄(`scheduler/jobs.py`), 관측성(`observability.py`) |

`migrations/` 는 레거시 포트폴리오 단계에서의 PostgreSQL 스키마 참고물로 남아 있을 수 있습니다. 현재 앱 부팅에는 **필요 없습니다.**

## 실행 흐름

1. Uvicorn이 앱을 띄우면 APScheduler 가 등록된 cron 작업을 시작합니다 (**18:00** 트렌드, **18:10** 인기 — 로컬 시각).
2. 클라이언트가 `GET /trends/{category}` 또는 `GET /popular/{context}` 를 호출하면, 라우터는 Redis 에서만 읽습니다.
3. 운영자가 `POST /collect/trigger` 로 `targets: ["trends"|"popular", ...]` 를 보내면, 해당 `runner` 작업이 **BackgroundTasks** 로 비동기 실행됩니다.

## 관측성

`app/platform/observability.py`

- 모든 요청: `X-Request-Id` 미들웨어(없으면 생성, 응답에 에코)
- `GET /healthz` — 프로세스 liveness
- `GET /readyz` — **Redis 연결**(ping); DB는 검사하지 않음
- `GET /metrics` — `prometheus_fastapi_instrumentator` 가능 시 노출

## 인증 모델

- 일반 라우터: 헤더 `X-API-Key` 의 SHA-256 이 `API_KEY_HASH` 와 일치
- 관리 수집: `ADMIN_API_KEY_HASH` 에 대응하는 관리자 키

401/403 구분 및 구현 세부는 `app/platform/core/auth.py` 를 참고합니다.
