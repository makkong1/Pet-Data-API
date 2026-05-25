# pet-data-api 아키텍처

## 개요

Naver 블로그 기반 **트렌드 키워드** · **인기 시설** 데이터를 수집해 두 가지 형태로 제공하는 Python 서비스.

| 제공 방식 | 대상 | 설명 |
|---|---|---|
| FastAPI HTTP | Petory recommendation 도메인 | `GET /popular/{context}`, `GET /trends/{category}` |
| Python batch CLI | Spring locationservice DB | `cli.py popular --output <path>` → JSON 파일 → Spring import |

PostgreSQL 없음. 영속 상태는 Redis(서버 모드)와 CLI 출력 파일뿐.

---

## 컴포넌트 구조

```
pet-data-api/
├── cli.py                        # 배치 진입점 (argparse)
├── app/
│   ├── main.py                   # FastAPI 앱 (lifespan: scheduler 시작/종료)
│   ├── ingestion/
│   │   ├── naver.py              # Naver 검색 API 호출 (httpx async)
│   │   ├── blog.py               # 블로그 파싱
│   │   ├── location.py           # 위치 정보 보강 (map_x/map_y → lat/lng)
│   │   ├── local_discovery.py    # boarding/hotel 전용 수집 경로
│   │   ├── runner.py             # run_popular_collection / run_trend_collection
│   │   ├── exporter.py           # CLI용: popular 결과 → LocationImportDto dict
│   │   └── analyzer/
│   │       ├── morpheme.py       # kiwipiepy 형태소 분석
│   │       └── trend.py          # 트렌드 키워드 집계
│   ├── serving/api/
│   │   ├── popular.py            # GET /popular/{context}
│   │   ├── trends.py             # GET /trends/{category}
│   │   └── collect.py            # POST /collect/trigger
│   └── platform/
│       ├── cache/redis.py        # Redis 클라이언트 (get_redis, get_trend 등)
│       ├── core/
│       │   ├── config.py         # pydantic-settings (API_KEY_HASH, NAVER_*)
│       │   └── auth.py           # require_api_key / require_admin_key
│       ├── scheduler/jobs.py     # APScheduler: 18:00 trend, 18:10 popular
│       ├── schemas/popular.py    # PopularEntry Pydantic 모델
│       └── observability.py      # Prometheus metrics, request-id
```

---

## 데이터 흐름

### 경로 A — FastAPI 서버 (Petory recommendation 소비)

```
APScheduler (매일 18:00/18:10)
  └── run_trend_collection()  → Naver 블로그 검색 → kiwipiepy 형태소
        → Redis ZSET  trends:{category}:keywords
  └── run_popular_collection() → Naver 블로그 검색 → 위치 보강
        → Redis JSON  popular:{context}

Petory RecommendService
  └── GET /popular/{context}  ← Redis popular:{context}
  └── GET /trends/{category}  ← Redis trends:{category}:keywords
```

### 경로 B — Python batch CLI (locationservice DB 적재)

```
cron / GitHub Actions
  └── python cli.py popular --output /data/popular.json
        └── collect_popular_for_cli(contexts)
              ├── collect_popular_for_context()   # 일반 컨텍스트
              ├── collect_popular_local_discovery() # boarding/hotel
              └── popular_dict_to_dto()            # map_x/map_y → lat/lng 변환
        → popular.json  (LocationImportDto 배열)

Spring FacilitySyncScheduler (매일 01:00)
  └── LocationImportService.importFromFile(path)
        └── Spring locationservice DB upsert
```

Redis 쓰기 없음. 두 경로는 완전히 독립적.

---

## 인증

| 헤더 | 검증 | 통과 조건 |
|---|---|---|
| `X-API-Key` | `require_api_key` | `API_KEY_HASH` 또는 `ADMIN_API_KEY_HASH` 일치 |
| `X-API-Key` | `require_admin_key` | `ADMIN_API_KEY_HASH` 만 일치 |

키 검증: `hashlib.sha256(key.encode()).hexdigest()` 와 저장된 hash 비교 (평문 저장 없음).

`POST /collect/trigger` 는 `require_admin_key` 만 통과.

---

## Redis 키 설계

| 키 패턴 | 타입 | 내용 |
|---|---|---|
| `popular:{context}` | string (JSON) | `List[PopularEntry]` — 인기 시설 목록 |
| `trends:{category}:keywords` | zset | member=키워드, score=언급수 |
| `trends:{category}:updated_at` | string | ISO8601 타임스탬프 |

컨텍스트: `grooming hospital supplies pharmacy cafe pension restaurant boarding hotel`

---

## 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `API_KEY_HASH` | Y | 일반 API 키의 SHA-256 hex |
| `ADMIN_API_KEY_HASH` | Y | 관리자 API 키의 SHA-256 hex |
| `NAVER_CLIENT_ID` | Y | Naver Open API 클라이언트 ID |
| `NAVER_CLIENT_SECRET` | Y | Naver Open API 시크릿 |
| `REDIS_URL` | Y | `redis://localhost:6379/0` |
| `NAVER_TIMEOUT_MS` | N | Naver API 타임아웃 ms (기본 10000) |

---

## API 엔드포인트

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| GET | `/healthz` | 없음 | Liveness |
| GET | `/readyz` | 없음 | Redis ping |
| GET | `/metrics` | 없음 | Prometheus |
| GET | `/popular/{context}` | 일반/관리자 | Redis 인기 시설 목록 |
| GET | `/trends/{category}` | 일반/관리자 | Redis 트렌드 키워드 |
| POST | `/collect/trigger` | 관리자 | 수동 배치 실행 |

---

## exporter.py — LocationImportDto 변환 규칙

CLI가 Spring locationservice 포맷으로 변환할 때의 규칙:

| Naver 필드 | Spring 필드 | 변환 |
|---|---|---|
| `map_y` | `lat` | `float(val) / 1e7` |
| `map_x` | `lng` | `float(val) / 1e7` |
| `road_address` or `address` | `address` | road_address 우선 |
| address 첫 토큰 | `sido` | `parts[0]` |
| address 두 번째 토큰 | `sigungu` | `parts[1]` |
| `telephone` | `phone` | 그대로 |
| (고정값) | `status` | `"운영중"` |

`boarding`, `hotel` 컨텍스트는 `collect_popular_local_discovery()` 경로 사용.
