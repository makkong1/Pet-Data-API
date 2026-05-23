# pet-data-api 실행 가이드

이 문서는 **현재 코드** (`app/main.py`, `app/serving/api/*`, `app/ingestion/runner.py`) 기준입니다. 인프라 최소 요구사항은 **Redis** 와 네이버 개발자 **Client ID/Secret** 입니다. PostgreSQL 마이그레이션은 **필요 없습니다.**

- 개요: [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md)
- 배치→API 흐름: [`분석/DATA-AND-API-FLOW.md`](분석/DATA-AND-API-FLOW.md)
- 에이전트 요약: 루트 [`CLAUDE.md`](../CLAUDE.md)

---

## 1. 의존성 설치 · 기동

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 이미 있다면 건너뜀 — 값 수정
redis-server           # 또는 Docker 등으로 REDIS_URL 이 가리키는 인스턴스 기동

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger: `http://localhost:8000/docs`

---

## 2. 환경 변수 (.env)

| 변수 | 필수 | 설명 |
|------|:----:|------|
| `API_KEY_HASH` | ✓ | 일반 클라이언트용 평문 API 키의 SHA-256 hex |
| `ADMIN_API_KEY_HASH` | ✓ | 관리자 키(수동 수집) SHA-256 hex |
| `NAVER_CLIENT_ID` | ✓ | 네이버 블로그 검색 API |
| `NAVER_CLIENT_SECRET` | ✓ | 위와 쌍 |
| `REDIS_URL` | 기본값 있음 | 예: `redis://localhost:6379/0` |
| `NAVER_TIMEOUT_MS` | 선택 | 기본 `10000` |

해시 생성 예:

```bash
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print('KEY=', k); print('HASH=', hashlib.sha256(k.encode()).hexdigest())"
```

일반 호출과 관리 호출 모두 헤더 이름은 **`X-API-Key`** 입니다. 관리 라우터는 평문 키가 `ADMIN_API_KEY_HASH` 에 대응할 때만 통과합니다.

---

## 3. 엔드포인트 요약

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| GET | `/healthz` | 없음 | Liveness |
| GET | `/readyz` | 없음 | **Redis** ping |
| GET | `/metrics` | 없음 | Prometheus (라이브러리 있으면) |
| GET | `/trends/{category}` | `X-API-Key` | Redis 트렌드 키워드 순위 |
| GET | `/popular/{context}` | `X-API-Key` | Redis 인기 상호 JSON 배열 |
| POST | `/collect/trigger` | 관리자 `X-API-Key` | JSON `{"targets":["trends","popular"]}` |

### 3.1 트렌드 카테고리

`app/ingestion/naver.py` 의 `CATEGORY_KEYWORDS` 키와 동일해야 합니다. 예:

`supplies`, `snack`, `food`, `grooming`, `hospital`, `clothes`, `pharmacy`, `cafe`, `pension`, `restaurant`, `boarding`, `hotel`

### 3.2 인기(Popularity) 컨텍스트

기본 허용: `grooming`, `hospital`, `supplies`, `pharmacy`, `cafe`, `pension`, `restaurant`, `boarding`, `hotel`

별칭: `snack`, `food`, `clothes` → 내부적으로 `supplies` 로 매핑.

---

## 4. curl 예시

`API_KEY` / `ADMIN_KEY` 는 `.env` 를 만든 뒤 직전에 출력한 평문 키 문자열입니다.

```bash
export API_KEY='<일반 평문 키>'
export ADMIN_KEY='<관리자 평문 키>'

curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/readyz

curl -s -H "X-API-Key: $API_KEY" "http://localhost:8000/trends/grooming?limit=10"
curl -s -H "X-API-Key: $API_KEY" "http://localhost:8000/popular/grooming?limit=10"

curl -s -X POST http://localhost:8000/collect/trigger \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"targets":["trends","popular"]}'
```

응답에 `collection started` 가 오면 배치가 백그라운드에서 실행됩니다. 테스트 환경에서 FastAPI/`BackgroundTasks` 동작 방식을 유의하세요.

---

## 5. 테스트

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

Redis 및 네이버 키가 없으면 일부 테스트는 스킵되거나 실패할 수 있습니다(프로젝트 테스트 정책에 따름).

---

## 6. 스케줄

앱 프로세스가 살아 있는 동안 APScheduler 가 로컬 시각 기준으로:

- **18:00** — `run_trend_collection`
- **18:10** — `run_popular_collection`

을 각각 실행합니다. [`../app/platform/scheduler/jobs.py`](../app/platform/scheduler/jobs.py).
