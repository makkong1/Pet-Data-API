# pet-data-api 아키텍처

## 역할 한 줄 요약

Naver 블로그 검색 결과를 파싱해 **인기 시설**·**트렌드 키워드**를 수집하고, Petory에 두 가지 방식으로 제공하는 Python 서비스.

---

## Petory와의 연결 구조

```text
pet-data-api                          Petory
─────────────────────────────────────────────────────────────────
[경로 A] FastAPI HTTP 실시간
  APScheduler (18:00/18:10)
    └─ run_trend_collection()  ──→ Redis trends:{category}:keywords
    └─ run_popular_collection() ──→ Redis popular:{context}
                                            ↓
                               RecommendService.recommendWithPetoryCandidates()
                                 fetchPopular()  ──→ GET /popular/{context}
                                 fetchTrends()   ──→ GET /trends/{category}

[경로 B] Batch CLI → 파일 → Spring DB
  cli.py popular --output ~/data/pet-locations.json
    └─ collect_popular_for_cli()
         └─ exporter.popular_dict_to_dto()
              └─ ~/data/pet-locations.json  (LocationImportDto JSON 배열)
                          ↓
         FacilitySyncScheduler (매일 01:00)
           └─ LocationImportService.importFromFile()
                └─ locationservice DB upsert (BATCH_IMPORT)
```

두 경로는 독립적으로 운영된다. 경로 A는 Redis만 읽는 HTTP 서버, 경로 B는 Redis 없이 JSON 파일만 출력하는 CLI.

---

## 컨텍스트 목록

| context | 수집 방식 | Petory Track |
|---------|----------|--------------|
| grooming | Naver blog → enrich_with_location | A (DB candidates + popular 병합) |
| hospital | Naver blog → enrich_with_location | A |
| pharmacy | Naver blog → enrich_with_location | A |
| cafe | Naver blog → enrich_with_location | A |
| restaurant | Naver blog → enrich_with_location | A |
| pension | Naver blog → enrich_with_location | A |
| boarding | local_discovery (2단계: discover → blog verify) | A |
| hotel | local_discovery (2단계: discover → blog verify) | A |
| supplies | Naver blog → enrich_with_location | B only (HTTP proxy — DB 병합 없음) |

`boarding`, `hotel`은 `_LOCAL_DISCOVERY_CONTEXTS`로 분류되어 `enrich_with_location` 스킵.
`supplies`는 현재 `PETORY_OWNED_CONTEXTS`에 미포함 → `recommendWithLegacyProxy()`만 호출.

---

## 경로 A 상세 — FastAPI HTTP 실시간

### 수집 파이프라인 (runner.py)

```text
APScheduler
  18:00 → run_trend_collection()
    for category in CATEGORY_KEYWORDS:
      collect_category_trends()      # Naver blog+cafe 검색
      save_posts()                   # SQLite raw_posts (원본 보존)
      aggregate_keywords()           # kiwipiepy 형태소 → Counter
      save_trend(category, counts)   # Redis ZSET trends:{category}:keywords

  18:10 → run_popular_collection()
    for context in _POPULAR_CONTEXTS:
      collect_popular_for_context()  # 일반 context (Naver blog 파싱)
      또는
      collect_popular_local_discovery() # boarding/hotel 전용
      enrich_with_location()         # Naver Local API → map_x/map_y 보강
      save_popular(context, popular) # Redis JSON popular:{context}
```

### Petory 소비 (RecommendService.java)

```text
POST /api/v1/recommend
  → isPetoryOwnedContext(context)?
      YES → recommendWithPetoryCandidates()
              fetchPopular(context, 20)    # GET /popular/{context}?limit=20
              fetchTrends(context, 15)     # GET /trends/{category}
              searchLocationServicesByLocation(lat, lng, 10km, category, 20)  # DB 반경 검색
              mergeNearbyCandidates()      # DB candidates + popular signal 병합
              → 응답
      NO  → recommendWithLegacyProxy()    # supplies 해당
              petDataApiClient.recommend() # 내부에서 fetchPopular + fetchTrends
              DB 병합 없음
```

### Redis 키

| 키 | 타입 | TTL | 내용 |
|----|------|-----|------|
| `popular:{context}` | string (JSON) | 25h | `List[PopularEntry]` |
| `trends:{category}:keywords` | ZSET | 24h | member=키워드, score=언급수 |
| `trends:{category}:updated_at` | string | 24h | ISO8601 타임스탬프 |

### HTTP 응답 → Petory 파싱 필드

`GET /popular/{context}?limit=1~20` → `PetDataApiClient.PopularEntryPayload`

| `PopularEntry` 필드 | Java 매핑 | 설명 |
|---------------------|-----------|------|
| `name` | `name` | 시설명 |
| `mention_count` | `mentionCount` | 블로그 언급 수 |
| `score` | `score` | 인기 점수 |
| `address` | `address` | 지번 주소 |
| `road_address` | `roadAddress` | 도로명 주소 |
| `map_x` | `mapX` | 경도 × 10⁷ 문자열 |
| `map_y` | `mapY` | 위도 × 10⁷ 문자열 |
| `telephone` | `telephone` | 전화번호 |
| `avg_freshness` | _(무시)_ | Java `@JsonIgnoreProperties`로 스킵 |

좌표 역변환: `float(val) / 1e7` (Python) = `/ 10_000_000.0` (Java).

---

## 경로 B 상세 — Batch CLI → Spring DB

### CLI 실행

```bash
PYTHONPATH=. python cli.py popular --output ~/data/pet-locations.json
# 특정 컨텍스트만:
PYTHONPATH=. python cli.py popular --output ~/data/pet-locations.json --contexts grooming hospital
```

### exporter.py 변환 규칙 (popular_dict_to_dto)

| Naver 필드 | LocationImportDto 필드 | 변환 |
|-----------|----------------------|------|
| `road_address` or `address` | `address` | road_address 우선 |
| address 첫 토큰 | `sido` | `parts[0]` |
| address 두 번째 토큰 | `sigungu` | `parts[1]` |
| `map_y` | `lat` | `float(val) / 1e7` |
| `map_x` | `lng` | `float(val) / 1e7` |
| `telephone` | `phone` | 그대로 |
| (CLI 인자) | `category` | context 문자열 |
| (고정) | `status` | `"운영중"` |

Redis 쓰기 없음. `collect_popular_for_cli()`는 `run_popular_collection()`과 동일 로직에서 `save_popular()` 호출만 제거한 버전.

### Spring 수신 (FacilitySyncScheduler → LocationImportService)

```text
FacilitySyncScheduler @Scheduled(01:00)
  app.location.import.file-path 설정 여부 확인
    미설정 → INFO 로그 후 스킵
    설정됨 → LocationImportService.importFromFile(path)
               ObjectMapper → List<LocationImportDto>
               for each dto:
                 isValid() 실패 → skipped++
                 findByNameAndAddressAndDataSource(name, address, "BATCH_IMPORT") 조회
                   존재(active)  → 필드 갱신 + lastUpdated=today + updated++
                   존재(deleted) → 재활성화(isDeleted=false) + 갱신 + updated++
                   없음          → batch insert + saved++
```

보존 필드 (갱신 금지): `rating`, `reviewCount`, `score`, `dataSource`.

---

## 컴포넌트 구조

```text
pet-data-api/
├── cli.py                        # 배치 진입점 (argparse)
├── app/
│   ├── main.py                   # FastAPI 앱 (lifespan: scheduler 시작/종료)
│   ├── ingestion/
│   │   ├── naver.py              # Naver 검색 API 호출 (httpx async)
│   │   ├── blog.py               # 블로그 파싱, collect_popular_for_context
│   │   ├── location.py           # Naver Local API → map_x/map_y 보강
│   │   ├── local_discovery.py    # boarding/hotel 전용 2단계 파이프라인
│   │   ├── record.py             # Naver blog/cafe 원본 레코드 모델
│   │   ├── runner.py             # run_popular_collection / run_trend_collection
│   │   ├── exporter.py           # CLI 전용: popular → LocationImportDto 변환
│   │   └── analyzer/
│   │       ├── morpheme.py       # kiwipiepy 형태소 분석
│   │       └── trend.py          # 트렌드 키워드 집계
│   ├── serving/api/
│   │   ├── popular.py            # GET /popular/{context}
│   │   ├── trends.py             # GET /trends/{category}
│   │   └── collect.py            # POST /collect/trigger
│   └── platform/
│       ├── cache/redis.py        # Redis 클라이언트
│       ├── core/config.py        # pydantic-settings
│       ├── core/auth.py          # require_api_key / require_admin_key
│       ├── store/sqlite.py       # 트렌드 원본 포스트 SQLite 저장
│       ├── scheduler/jobs.py     # APScheduler 등록
│       ├── schemas/popular.py    # PopularEntry Pydantic 모델
│       ├── integration_trace.py  # 요청별 추적 로그
│       ├── ingestion_digest.py   # 배치 저장 요약 로그
│       └── observability.py      # Prometheus metrics, request-id
```

---

## API 엔드포인트

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| GET | `/healthz` | 없음 | Liveness |
| GET | `/readyz` | 없음 | Redis ping |
| GET | `/metrics` | 없음 | Prometheus |
| GET | `/popular/{context}` | 일반/관리자 | Redis 인기 시설 목록 (`?limit=1~20`, 기본 20) |
| GET | `/trends/{category}` | 일반/관리자 | Redis 트렌드 키워드 |
| POST | `/collect/trigger` | 관리자만 | 수동 배치 실행 (`?wait=true` → 200 + 결과) |

`snack`, `food`, `clothes` → `/popular/supplies` 로 alias 처리 (`normalizePopularPathContext`).

---

## 인증

| 헤더 | 검증 함수 | 통과 조건 |
|------|----------|----------|
| `X-API-Key` | `require_api_key` | `API_KEY_HASH` 또는 `ADMIN_API_KEY_HASH` 일치 |
| `X-API-Key` | `require_admin_key` | `ADMIN_API_KEY_HASH` 만 일치 |

`hashlib.sha256(key.strip().encode()).hexdigest()` 비교. 평문 저장 없음.

---

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `API_KEY_HASH` | Y | 일반 API 키 SHA-256 hex |
| `ADMIN_API_KEY_HASH` | Y | 관리자 API 키 SHA-256 hex |
| `NAVER_CLIENT_ID` | Y | Naver Open API ID |
| `NAVER_CLIENT_SECRET` | Y | Naver Open API 시크릿 |
| `REDIS_URL` | Y | `redis://localhost:6379/0` |
| `NAVER_TIMEOUT_MS` | N | Naver API 타임아웃 ms (기본 10000) |
| `SQLITE_PATH` | N | 트렌드 원본 SQLite 경로 (기본 `data/raw_posts.db`) |

---

## 알려진 미완성 항목

| 항목 | 상태 | 설명 |
|------|------|------|
| supplies Track A 편입 | 미완 | `PETORY_OWNED_CONTEXTS`에 추가 + DB candidates 병합 필요 |
| missing items 자동 soft-delete | 미완 | `lastUpdated < 기준일` row 탐지 정책 미결정 |
