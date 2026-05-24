# pet-data-api 실행 가이드

이 문서는 **현재 코드** (`app/main.py`, `app/serving/api/*`, `app/ingestion/runner.py`) 기준입니다. 인프라 최소 요구사항은 **Redis** 와 네이버 개발자 **Client ID/Secret** 입니다. PostgreSQL 마이그레이션은 **필요 없습니다.**

- 개요: [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md)
- 배치→API 흐름: [`분석/DATA-AND-API-FLOW.md`](분석/DATA-AND-API-FLOW.md)
- 에이전트 요약: 루트 [`CLAUDE.md`](../CLAUDE.md)

---

운영 시 로그 grep 참고:

- **`pet_data_api.petory_compat`** — `[petory-compat]` … `GET /trends`,`/popular` Redis 읽기(inbound/outbound) + **`POST /collect/trigger` 트리거 시점**(inbound, 그리고 배경예약/`wait=true` 완료 시 outbound).
- **`pet_data_api.ingestion_digest`** — `[ingestion-digest]` … 스케줄/수집 트리거로 **Redis 에 쓰기 직후** 카테고리별 블로그 건수·용어 수·미리보기, 인기 목록 요약·`batch_done`.
- **출력이 안 보이면**: 앱 시작 시 `app.*` 와 `pet_data_api.*` 에 **stderr 스트림 핸들러**를 붙이도록 설정됨 (`app/main.py` `_configure_logging`). 환경변수 **`LOG_LEVEL`**(기본 `INFO`), 선택 **`LOG_FMT`**.

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

이미 평문 키가 있을 때, `.env` 의 `ADMIN_API_KEY_HASH`(또는 `API_KEY_HASH`)와 같은지 확인하려면:

```bash
printf '%s' '여기-평문-관리자-키' | python3 scripts/sha256_key.py
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

# `uvicorn --reload` 때문에 백그라운드가 끊기는 경우: 동일 요청에서 끝까지 기다림 (HTTP 200, 본문에 results)
curl -s -X POST 'http://localhost:8000/collect/trigger?wait=true' \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"targets":["popular"]}'
```

응답 JSON의 `request_id`(또는 응답 헤더 `X-Request-Id`)와 터미널 로그의 `[request_id]` 를 맞춰 보면, 트리거 직후 `background ... START/DONE` 흐름을 추적하기 쉽습니다.

기본(`wait=false`)은 **즉시 202**이고 배경 작업은 **응답 본문을 보낸 뒤** 실행됩니다(Starlette 규격). `wait=true` 는 **같은 HTTP 요청이 끝날 때까지** 배치를 실행하므로, 로컬에서 파일 저장으로 워커가 재시작되면 안 되게 할 때 안전합니다.

`401` 에 `looks like SHA-256 hex … plaintext …` 메시지가 오면 **`X-API-Key` 에 .env의 해시(64자)`를 넣은 것입니다. 평문 키만 넣으세요.

---

## 4.1 수동 수집이 “안 된다고” 느껴질 때

| 증상 | 점검 |
|------|------|
| **부팅 직후** `Startup: Redis ping FAILED` | `REDIS_URL` 과 로컬 Redis(`requirepass`, 포트 등) 불일치. 이 상태면 트렌드/인기/수집 **쓰기 전부 실패**합니다. |
| **부팅 직후** `ADMIN_API_KEY_HASH must be exactly 64 hex` | `.env` 해시 줄에 공백·주석 침범 또는 비 hex 문자 포함. 수정 후 재기동. |
| **422**, `json_invalid` | 바디 문자열 깨짐(예 마지막 `}` 없음). 한 줄: `{\"targets\":[\"trends\"]}` 검증 권장. |
| **401**, `Missing X-API-Key header` | Swagger 에서 해당 엔드포인트 **Parameters 의 `X-API-Key` 칸 비움**(또는 curl 에 `-H` 누락). **관리 라우터는 평문 관리자 키** 필요. |
| **401**, `Invalid API Key` / **403**, `Admin key required` | 키는 넣었으나 평문이 해시와 안 맞음, 또는 일반 키로 관리 라우터 호출. |
| **422**, body `targets` 검증 등 | 헤더는 통과했는데 **`targets` 에 `popular`/`trends` 외 문자열**(또는 JSON 형식 깨짐). |
| **202** 인데 데이터가 안 바뀜 | `GET /readyz` 의 Redis 상태. 네이버 API 실패·집계 비어 스킵이면 카테고리별로 `skipped`/`failed` 가 될 수 있음 — 터미널 `INFO` 또는 `[ingestion-digest]` 로그 확인. |

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
