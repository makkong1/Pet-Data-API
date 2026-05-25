# Petory — recommendation 도메인

> 파일: `backend/main/java/com/linkup/Petory/domain/recommendation/`

## 역할

사용자의 위치와 반려동물 종류를 바탕으로 **주변 시설 추천** 및 **트렌드 키워드**를 제공한다.
Petory DB(locationservice)와 pet-data-api(외부 인기 신호) 두 소스를 결합해 응답을 구성한다.

---

## 주요 클래스

### Controller

**`RecommendController`** (`/api/recommend`)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/recommend` | 주변 시설 추천 (`lat`, `lng`, `context` 파라미터) |
| POST | `/api/recommend/copy` | 추천 카피 텍스트 생성 |
| POST | `/api/recommend/events` | 시설 클릭/조회 이벤트 수집 |
| GET | `/api/recommend/trends/{category}` | 트렌드 시계열 |

인증: Spring Security 세션 (`requireUserId()`).

---

### Service

**`RecommendService`**

**핵심 분기 로직:**

```
recommend(userId, lat, lng, context)
  └── isPetoryOwnedContext(context)?
        YES → recommendWithPetoryCandidates()   [Petory-owned 경로]
        NO  → recommendWithLegacyProxy()        [legacy proxy 경로]
```

**Petory-owned contexts:** `grooming, hospital, pharmacy, cafe, restaurant, pension, boarding, hotel`

#### Petory-owned 경로 (`recommendWithPetoryCandidates`)

1. `locationServiceService.searchLocationServicesByLocation()` → 반경 10km 내 최대 20개 후보
2. `petDataApiClient.fetchPopular(context)` → pet-data-api 인기 신호 (블로그 언급 기반)
3. `petDataApiClient.fetchTrends(context)` → pet-data-api 트렌드 키워드
4. `mergeNearbyCandidates()` → 후보 + 인기 신호 결합, 점수 계산 후 상위 5개 선택

**점수 산식 (finalScore):**

```
finalScore = 거리점수 × 0.55
           + 평점점수 × 0.20
           + 리뷰점수 × 0.15
           + 인기점수 × 0.10
```

- 거리점수: `1 - (distanceM / 10000)`, 클수록 가까움
- 인기점수: `mentionScore(×0.6) + mentionCount(×0.4)`, 최댓값 정규화

**이름 매칭:** `buildNameAliases()` — 시설명에서 카테고리 접미사 제거 후 fuzzy 인덱싱
(예: "멍멍미용실" → ["멍멍미용실", "멍멍"] 모두 인덱싱)

#### legacy proxy 경로 (`recommendWithLegacyProxy`)

non-PETORY_OWNED_CONTEXTS (e.g. supplies, snack, food, clothes)는 `petDataApiClient.recommend()`를 그대로 통과시킨다. pet-data-api가 popular + trends를 조합해 반환.

---

### Client

**`PetDataApiClient`** — pet-data-api HTTP 클라이언트

| 메서드 | 호출 엔드포인트 | 설명 |
|---|---|---|
| `fetchPopular(context, limit, correlationId)` | `GET /popular/{context}` | Redis 인기 시설 목록 |
| `fetchTrends(context, limit, correlationId)` | `GET /trends/{category}` | Redis 트렌드 키워드 |
| `recommend(request)` | popular + trends 조합 | legacy proxy용 래퍼 |
| `recommendCopy(request)` | (로컬 규칙 기반) | 추천 카피 텍스트 생성 (HTTP 없음) |
| `getTrendTimeseries(category, days, topN)` | `GET /trends/{category}` | 스냅샷을 N일치 포인트로 확장 |
| `sendEvents(request)` | (skip) | 이벤트 수집 미구현, 로그만 |
| `fetchAllFacilities(pageSize)` | (미사용) | `/facilities` 삭제됨, dead code |

**설정값:**

```properties
app.pet-data-api.base-url=http://localhost:8000
app.pet-data-api.api-key=<plain key>
app.pet-data-api.timeout-ms=3000
app.pet-data-api.copy-timeout-ms=35000   # 현재 미사용
```

인증 헤더: `X-API-Key: <plain key>` (Spring → pet-data-api).

---

## 데이터 흐름 (Petory-owned 경로)

```
FE: GET /api/recommend?lat=37.5&lng=127.0&context=grooming
  ↓
RecommendController.recommend()
  ↓
RecommendService.recommend()
  ├── locationServiceService.searchLocationServicesByLocation()
  │     → Petory MySQL (ST_Distance_Sphere, radius=10km, category="미용")
  │     → 최대 20개 LocationServiceDTO
  │
  ├── petDataApiClient.fetchPopular("grooming", 20)
  │     → GET http://pet-data-api:8000/popular/grooming
  │     → Redis popular:grooming JSON
  │
  ├── petDataApiClient.fetchTrends("grooming", 15)
  │     → GET http://pet-data-api:8000/trends/grooming
  │     → Redis trends:grooming:keywords ZSET
  │
  └── mergeNearbyCandidates()
        → 거리 55% + 평점 20% + 리뷰 15% + 인기 10% 점수
        → 상위 5개 FacilityItem
  ↓
RecommendResponse(context, version="petory-nearby-v1", facilities[], trends[], recommendation)
```

---

## 이벤트 수집

`POST /api/recommend/events`로 시설 클릭/조회 이벤트를 수신한다.
`userId`는 SHA-256 앞 12자리 hex (`petory-xxxxxxxxxx`)로 익명화 후 `petDataApiClient.sendEvents()` 호출.
현재 pet-data-api에 이벤트 수집 엔드포인트 없음 — `sendEvents()`는 debug 로그만 출력.

---

## 의존 관계

```
RecommendService
  ├── PetRepository           (Petory user 도메인)
  ├── PetDataApiClient        → pet-data-api HTTP
  └── LocationServiceService  → Petory locationservice DB
```
