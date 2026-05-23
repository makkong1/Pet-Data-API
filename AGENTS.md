# AGENTS.md — pet-data-api

네이버 블로그 기반 **반려 트렌드 키워드**(Redis)·**컨텍스트별 인기 상호**(Redis)를 제공하는 FastAPI 마이크로 API. 규격은 루트 [`CLAUDE.md`](CLAUDE.md) 상단과 동일합니다.

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 목적 | 배치가 네이버 결과를 적재하면, HTTP는 Redis만 조회한다 |
| 포지션 | Petory(Java/Spring)와 병행 멀티스택 백엔드 포트폴리오 |
| 영속 DB | 현재 레포에서는 **PostgreSQL 미사용** |

## 기술 스택

| 역할 | 기술 |
|------|------|
| 웹 프레임워크 | FastAPI |
| 캐시 | Redis (`redis-py` asyncio; 키: `app/platform/cache/redis.py`) |
| 형태소 | kiwipiepy (트렌드 수집) |
| 스케줄러 | APScheduler (로컬 18:00 트렌드, 18:10 인기, `max_instances=1`) |
| HTTP 클라이언트 | httpx(async) |
| 인증 | `X-API-Key` 헤더 → SHA-256 비교 |

## 실행

```bash
source venv/bin/activate
pip install -r requirements.txt
# Redis + .env
uvicorn app.main:app --reload

PYTHONPATH=. pytest tests/ -v
```

## 환경변수

`.env.example` 참고. 최소 `{API_KEY_HASH, ADMIN_API_KEY_HASH, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, REDIS_URL}`.

```bash
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print('plain=', k); print('hash=', hashlib.sha256(k.encode()).hexdigest())"
```

## 프로젝트 구조

```
pet-data-api/
├── app/
│   ├── main.py
│   ├── ingestion/    # 네이버 블로그 수집·집계
│   ├── serving/api/ # trends / popular / collect
│   └── platform/    # config, auth, redis, scheduler, observability
├── migrations/       # 레거시 SQL (앱 실행에 불필요)
└── tests/
```

## 아키텍처 핵심

- 배치만 네이버 호출 (`runner.py`); API 라우터는 Redis만 읽는다.
- `/readyz` 는 **Redis ping** 만 검사한다.
- `POST /collect/trigger` 는 JSON `{"targets":["trends","popular"]}` 와 관리자 키 필요.

## API 요약

| 메서드 | 경로 |
|--------|------|
| GET | `/healthz`, `/readyz`, `/metrics` |
| GET | `/trends/{category}` |
| GET | `/popular/{context}` |
| POST | `/collect/trigger` |

## 문서

[`docs/PROJECT-OVERVIEW.md`](docs/PROJECT-OVERVIEW.md), [`docs/USAGE.md`](docs/USAGE.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
