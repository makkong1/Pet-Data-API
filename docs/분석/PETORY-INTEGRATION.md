# Petory ↔ pet-data-api 연동 가이드

> 대상: Petory(Java/Spring) 백엔드 — `PetDataApiClient.java`  
> pet-data-api는 **Redis에 캐시된 트렌드 키워드·인기 상호 및 시설 목록**을 제공합니다. PostgreSQL·추천·이벤트 콜백 없음.

짝 문서: [`USAGE.md`](USAGE.md) (curl·환경변수), [`V3-CHANGES.md`](V3-CHANGES.md) (변경 타임라인)

---

## 1. API 요약

| 엔드포인트               | 설명                                            | 인증               |
| ------------------------ | ----------------------------------------------- | ------------------ |
| `GET /popular/{context}` | 업종별 인기 상호 목록 (최대 20)                 | `X-API-Key` 일반   |
| `GET /trends/{category}` | 카테고리 트렌드 키워드 순위                     | `X-API-Key` 일반   |
| `GET /facilities`        | cursor 기반 시설 목록 (FacilitySyncService용)   | `X-API-Key` 일반   |
| `GET /healthz`           | Liveness                                        | 없음               |
| `GET /readyz`            | Redis Readiness                                 | 없음               |
| `POST /collect/trigger`  | 배치 수동 실행                                  | `X-API-Key` 관리자 |

**유효 context/category**: `grooming` `hospital` `supplies` `pharmacy` `cafe` `pension` `restaurant` `boarding` `hotel`

**별칭** (popular만): `snack` `food` `clothes` → `supplies` 로 서버 정규화

---

## 2. Petory 클라이언트 필수 헤더

```http
X-API-Key: <평문 API 키>       # 필수 — .env의 해시가 아닌 원래 평문
X-Request-Id: <16자 hex>        # 권장 — pet-data-api가 동일 값을 응답 헤더에 에코
X-Caller-Service: petory        # 권장 — 로그에서 Petory 요청 식별용
```

`PetDataApiClient.buildClient()` 에서 `defaultHeader` 로 고정 설정:

```java
return RestClient.builder()
    .baseUrl(baseUrl)
    .defaultHeader("X-API-Key", apiKey)
    .defaultHeader("X-Caller-Service", "petory")   // 추가
    .requestFactory(factory)
    .build();
```

`X-Request-Id`는 이미 `withOptionalCorrelation()` 로 요청별 주입 중 → **변경 불필요**.

---

## 3. 요청 추적 — 로그 한 사이클

Petory가 `GET /popular/cafe?limit=5` (X-Request-Id: `a1b2c3d4`, X-Caller-Service: `petory`) 를 보내면:

```text
# 1. 요청 진입 (AccessLogMiddleware)
2026-05-24 18:00:01 INFO pet_data_api.access
  [a1b2c3d4] --> GET /popular/cafe query=limit=5 ip=10.0.0.1 caller=petory rid_src=caller

# 2. 엔드포인트 파라미터 (integration_trace.inbound)
2026-05-24 18:00:01 INFO pet_data_api.petory_compat
  [a1b2c3d4] inbound op=popular caller=petory rid_src=caller path=/popular/cafe ...

# 3. Redis 조회 결과 (integration_trace.outbound_redis_hit)
2026-05-24 18:00:01 INFO pet_data_api.petory_compat
  [a1b2c3d4] outbound op=popular status=200 redis_key='popular:cafe'
  in_cache=3 returning=3 sample_names=['온독', '바닐라브릭', ...]

# 4. 응답 완료 (AccessLogMiddleware)
2026-05-24 18:00:01 INFO pet_data_api.access
  [a1b2c3d4] <-- 200 elapsed_ms=5 path=/popular/cafe caller=petory
```

**grep 패턴:**

```bash
grep 'caller=petory' app.log          # Petory 요청만
grep 'a1b2c3d4' app.log               # 특정 request_id 전체 추적
grep 'auth 40' app.log                # 인증 실패 전체
grep 'status=503.*op=popular' app.log # popular 캐시 비어있음
grep 'ingestion-digest' app.log       # 배치 수집 결과
```

**rid_src 해석:**

| 값                  | 의미                                                             |
| ------------------- | ---------------------------------------------------------------- |
| `rid_src=caller`    | Petory가 `X-Request-Id` 를 보냄 — Petory 로그와 cross-trace 가능 |
| `rid_src=generated` | pet-data-api가 자체 생성 — 단독 추적만 가능                      |

---

## 4. 에러 응답 패턴

| HTTP | 메시지                   | 원인                                 | 대처                             |
| ---- | ------------------------ | ------------------------------------ | -------------------------------- |
| 401  | Missing X-API-Key header | 헤더 누락                            | 헤더 추가                        |
| 401  | Invalid API Key          | 평문 키 오류 또는 해시를 헤더에 넣음 | .env 평문 키 확인                |
| 403  | Admin key required       | 일반 키로 관리자 경로 호출           | `/collect/trigger`는 관리자 키만 |
| 404  | Unknown context/category | 잘못된 경로 파라미터                 | §1 유효값 목록 참조              |
| 503  | popular data unavailable | Redis 키 없음 (배치 미실행)          | 빈 배열로 fallback 후 대기       |
| 503  | Cache unavailable        | Redis 연결 오류                      | `/readyz` 로 Redis 상태 확인     |

`popular` 503 수신 시 권장 처리: 인기 카드 숨김, 빈 배열 반환, 재시도 없이 다음 배치 대기.

---

## 5. 데이터 파이프라인 현황

### 배치 스케줄

| 작업        | 시각              | 설명                                         |
| ----------- | ----------------- | -------------------------------------------- |
| 트렌드 수집 | 매일 18:00 (로컬) | 블로그+카페 → 형태소 분석 → Redis Sorted Set |
| 인기 수집   | 매일 18:10 (로컬) | 블로그+카페 → 상호명 추출·점수 → Redis JSON  |

수동 트리거 (관리자 키):

```http
POST /collect/trigger
X-API-Key: <admin-plaintext-key>
Content-Type: application/json

{"targets": ["popular", "trends"]}
```

### 데이터 소스

- **네이버 블로그 검색 API** (`blog.json`)
- **네이버 카페 검색 API** (`cafearticle.json`) — 2026-05-24 배치부터 병합 적용

쿼터: 블로그+카페 합산 **25,000건/일** (같은 Client ID 공유).

### Redis 키 TTL

| Redis 키                     | TTL | 설명                                     |
| ---------------------------- | --- | ---------------------------------------- |
| `trends:{category}:keywords` | 24h | 카테고리별 키워드 Sorted Set             |
| `popular:{context}`          | 25h | 인기 상호 JSON (배치 주기 24h + 여유 1h) |

### 알려진 데이터 품질 이슈

| 증상                                | 원인                                | 상태                      |
| ----------------------------------- | ----------------------------------- | ------------------------- |
| `in_cache=3` (popular 항목 수 적음) | 카페 상호명 패턴 다양 → 추출률 낮음 | 배치 재실행으로 개선 예정 |
| `'진짜'` 같은 부사가 상호명 포함    | blocklist 미등록                    | 수정 예정                 |

---

## 6. FacilitySyncService 연동 (GET /facilities)

Petory의 `FacilitySyncScheduler`는 매일 01:00 pet-data-api `GET /facilities`를 호출하여 시설 데이터를 Petory `LocationService` DB에 동기화한다.

### 페이징 방식

```
cursor=0 → items(100) + next_cursor=100
cursor=100 → items(100) + next_cursor=200
...
has_next=false → 수집 완료
```

### 응답 스키마

```json
{
  "items": [
    {
      "name": "해피독 미용실",
      "category": "grooming",
      "address": "서울시 마포구 ...",
      "region_city": "서울",
      "region_district": "마포구",
      "phone": "02-1234-5678",
      "lat": 37.5672,
      "lng": 126.9765,
      "status": "active"
    }
  ],
  "next_cursor": 100,
  "has_next": true
}
```

### 쿼리 파라미터

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `cursor` | `0`    | 시작 오프셋 |
| `limit`  | `100`  | 페이지 크기 (최대 500) |

### 데이터 출처

`popular:{context}` Redis 키를 전체 스캔하여 `address` 필드가 있는 항목만 반환. `map_x`/`map_y` → `lat`/`lng` 자동 변환, `name`+`address` 기준 중복 제거.

---

## 7. 폐기된 엔드포인트

Petory 코드에 다음 경로가 남아 있으면 dead code 또는 404 원인:

- `POST /recommend`, `POST /recommend/copy`
- `GET /stats/summary`
- `POST /events/recommendation`
- `GET /trends/{category}/timeseries` (Postgres 시계열)
